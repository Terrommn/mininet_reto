#!/usr/bin/env python3
# script de prueba: levanta la red, valida todo y da un reporte OK/FALLO
# ejecutar: sudo python3 test_red.py
import re
import os
import sys
import time
from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel
from site_a1 import SiteA1
from site_a2 import SiteA2
from site_b1 import SiteB1
from site_b2 import SiteB2
from master_wan import WAN, write_configs, DHCP_CONF, DNS_CONF

PASS = []
FAIL = []


def check(desc, ok):
    (PASS if ok else FAIL).append(desc)
    print(f"  [{'OK   ' if ok else 'FALLO'}] {desc}")
    return ok


def info(desc, ok):
    print(f"  [INFO {'si ' if ok else 'no '}] {desc}")


def ping_ok(src, dst):
    return '1 received' in src.cmd(f'ping -c1 -W2 {dst}')


def host_ip(host):
    intf = host.defaultIntf().name
    m = re.search(r'inet (10[.][0-9.]+)', host.cmd(f'ip -4 -o addr show {intf}'))
    return m.group(1) if m else None


def dhcp(host):
    intf = host.defaultIntf().name
    host.cmd(f'timeout 20 dhclient -v {intf} > /dev/null 2>&1')


def build(net):
    # misma orquestacion que master_wan, pero reutilizando su tabla WAN y write_configs
    a1, a2, b1, b2 = SiteA1(), SiteA2(), SiteB1(), SiteB2()
    sites = [a1, a2, b1, b2]
    spokes = {'a2': a2, 'b1': b1, 'b2': b2}
    for s in sites:
        s.build(net)
    for key, ip_hub, intf_hub, ip_spoke, bw in WAN:
        net.addLink(a1.border_router, spokes[key].gateway,
                    intfName1=intf_hub, intfName2=spokes[key].WAN_INTF, bw=bw, delay='10ms')
    net.start()
    for key, ip_hub, intf_hub, ip_spoke, bw in WAN:
        a1.border_router.setIP(ip_hub, intf=intf_hub)
        spokes[key].gateway.setIP(ip_spoke, intf=spokes[key].WAN_INTF)
    for s in sites:
        s.configure()
    # rutas wan generadas desde la tabla WAN (no hardcodeadas, para que no se desincronicen)
    r = a1.border_router
    for key, ip_hub, intf_hub, ip_spoke, bw in WAN:
        sp = spokes[key]
        r.cmd(f'ip route replace 10.{sp.SITE_ID}.0.0/16 via {ip_spoke.split("/")[0]} dev {intf_hub}')
        sp.gateway.cmd(f'ip route replace default via {ip_hub.split("/")[0]} dev {sp.WAN_INTF}')
    write_configs(sites)
    a1.start_services(DHCP_CONF, DNS_CONF)
    for s in sites:
        s.relay_target = a1.dhcp_server_ip
        s.start_relay()
    return net


def cleanup():
    for pat in ('dhcp_corp', 'dns_corp', 'pyftpdlib', 'http.server'):
        os.system(f'pkill -f {pat} 2>/dev/null')


def main():
    setLogLevel('warning')   # menos ruido de Mininet
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink,
                  autoSetMacs=True, autoStaticArp=False)
    print("== Levantando la red (4 sedes) ...")
    build(net)
    print("== Esperando a los servicios (dnsmasq / web / ftp) y al DHCP ...")
    time.sleep(5)
    try:
        ha1_10 = net.get('h-a1-v10')
        ha1_20 = net.get('h-a1-v20')
        ha2 = net.get('h-a2-v40')
        hb1 = net.get('h-b1-v50')
        hb2 = net.get('h-b2-v60')
        for h in (ha1_10, ha1_20, ha2, hb1, hb2):
            dhcp(h)
        time.sleep(1)

        print("\n[1] DHCP central + relay (cada sede recibe IP por el servidor de A1):")
        check("A1  h-a1-v10 obtuvo IP 10.1.10.x", (host_ip(ha1_10) or '').startswith('10.1.10.'))
        check("A2  h-a2-v40 obtuvo IP 10.2.40.x", (host_ip(ha2) or '').startswith('10.2.40.'))
        check("B1  h-b1-v50 obtuvo IP 10.3.50.x", (host_ip(hb1) or '').startswith('10.3.50.'))
        check("B2  h-b2-v60 obtuvo IP 10.4.60.x", (host_ip(hb2) or '').startswith('10.4.60.'))

        print("\n[2] Inter-VLAN local (Router-on-a-Stick en A1):")
        check("h-a1-v10 -> gateway de VLAN 20 (10.1.20.254)", ping_ok(ha1_10, '10.1.20.254'))
        if host_ip(ha1_20):
            check("h-a1-v10 -> h-a1-v20 (de VLAN 10 a VLAN 20)", ping_ok(ha1_10, host_ip(ha1_20)))

        print("\n[3] WAN hub-and-spoke:")
        check("A2 -> servidor web en A1 (10.1.100.4)", ping_ok(ha2, '10.1.100.4'))
        check("B2 -> servidor web en A1 (10.1.100.4)", ping_ok(hb2, '10.1.100.4'))
        if host_ip(hb1):
            check("A2 -> B1 (spoke a spoke, transito por el hub)", ping_ok(ha2, host_ip(hb1)))

        print("\n[4] DNS interno (dnsmasq):")
        check("dig @10.1.100.3 web.corp.local -> 10.1.100.4",
              '10.1.100.4' in ha2.cmd('dig +short @10.1.100.3 web.corp.local'))
        check("dig web.corp.local (DNS recibido por DHCP) -> 10.1.100.4",
              '10.1.100.4' in ha2.cmd('dig +short web.corp.local'))

        print("\n[5] Servidor Web (http.server):")
        check("curl http://10.1.100.4 (por IP)",
              'Datacenter' in ha2.cmd('curl -s --max-time 6 http://10.1.100.4'))
        check("curl http://web.corp.local (por FQDN)",
              'Datacenter' in hb2.cmd('curl -s --max-time 6 http://web.corp.local'))

        print("\n[6] Servidor FTP (pyftpdlib):")
        check("curl ftp://admin:***@10.1.100.5/ lista welcome.txt",
              'welcome.txt' in ha2.cmd('curl -s --max-time 6 ftp://admin:secret123@10.1.100.5/'))

        print("\n[7] Redundancia del doble nucleo (bajamos TODOS los enlaces de core1):")
        print("    (informativo: con rutas estaticas el failover depende del kernel)")
        for d in ('r-a1', 'srv-dhcp', 'srv-dns', 'srv-web', 'srv-ftp'):
            net.configLinkStatus(d, 'core1', 'down')
        time.sleep(2)
        info("A2 -> servidor sigue respondiendo via core2", ping_ok(ha2, '10.1.100.4'))
        for d in ('r-a1', 'srv-dhcp', 'srv-dns', 'srv-web', 'srv-ftp'):
            net.configLinkStatus(d, 'core1', 'up')
    finally:
        total = len(PASS) + len(FAIL)
        print(f"\n===== RESUMEN: {len(PASS)}/{total} pruebas OK =====")
        if FAIL:
            print("Fallaron:")
            for d in FAIL:
                print(f"  - {d}")
        net.stop()
        cleanup()
    sys.exit(0 if not FAIL else 1)


if __name__ == '__main__':
    main()
