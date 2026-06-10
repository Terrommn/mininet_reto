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

from master_wan import (
    WAN,
    write_configs,
    DHCP_CONF,
    DNS_CONF,
    dhclient_cmd,
    harden_rp_filter,
    prep_resolv,
)

PASS = []
FAIL = []


def check(desc, ok):
    (PASS if ok else FAIL).append(desc)
    print(f"  [{'OK   ' if ok else 'FALLO'}] {desc}")
    return ok


def info(desc, ok):
    print(f"  [INFO {'si ' if ok else 'no '}] {desc}")


def cleanup():
    os.system('pkill -9 -f "[d]hclient" 2>/dev/null || true')
    os.system('pkill -9 -f "[d]hcrelay" 2>/dev/null || true')
    os.system('pkill -9 -f "dhcp_corp" 2>/dev/null || true')
    os.system('pkill -9 -f "dns_corp" 2>/dev/null || true')
    os.system('pkill -9 -f "pyftpdlib" 2>/dev/null || true')
    os.system('pkill -9 -f "http.server" 2>/dev/null || true')


def ping_ok(src, dst):
    out = src.cmd(f'ping -c1 -W2 {dst}')
    return '1 received' in out or '1 packets received' in out


def host_ip(host):
    intf = host.defaultIntf().name
    out = host.cmd(f'ip -4 -o addr show {intf}')
    m = re.search(r'inet (10[.][0-9.]+)', out)
    return m.group(1) if m else None


def dhcp_log_ok(log, prefix):
    return (
        f'bound to {prefix}' in log
        or f'DHCPACK of {prefix}' in log
        or f'DHCPOFFER of {prefix}' in log
    )


def start_dhcp_probe(host):
    name = host.name
    intf = host.defaultIntf().name
    log = f'/tmp/dhcp-{name}.log'

    print(f"  - Probando DHCP en {name} ({intf})...", flush=True)

    host.cmd(f'ip addr flush dev {intf}')
    host.cmd(f'rm -f /tmp/dhcl-{name}.leases /tmp/dhcl-{name}.pid {log}')
    host.cmd(f'pkill -9 -f "[d]hclient.*{intf}" 2>/dev/null || true')

    host.cmd('mkdir -p /etc')
    host.cmd('touch /etc/fstab')
    host.cmd('chmod 644 /etc/fstab')
    host.cmd(f'touch /tmp/dhcl-{name}.leases /tmp/dhcl-{name}.pid')
    host.cmd(f'chmod 666 /tmp/dhcl-{name}.leases /tmp/dhcl-{name}.pid')

    cmd = dhclient_cmd(host)
    host.cmd(f'(timeout -k 2 -s KILL 20 {cmd}) > {log} 2>&1 &')


def read_dhcp_log(host):
    return host.cmd(f'cat /tmp/dhcp-{host.name}.log 2>/dev/null')


def set_static(host, ip, gw):
    intf = host.defaultIntf().name
    host.cmd(f'pkill -9 -f "[d]hclient.*{intf}" 2>/dev/null || true')
    host.cmd(f'ip addr flush dev {intf}')
    host.cmd(f'ip addr add {ip}/24 dev {intf}')
    host.cmd(f'ip route replace default via {gw}')
    host.cmd('rm -f /etc/resolv.conf')
    host.cmd('echo "nameserver 10.1.100.3" > /etc/resolv.conf')


def build(net):
    a1, a2, b1, b2 = SiteA1(), SiteA2(), SiteB1(), SiteB2()
    sites = [a1, a2, b1, b2]
    spokes = {'a2': a2, 'b1': b1, 'b2': b2}

    for s in sites:
        s.build(net)

    for key, ip_hub, intf_hub, ip_spoke, bw in WAN:
        sp = spokes[key]
        net.addLink(
            a1.border_router,
            sp.gateway,
            intfName1=intf_hub,
            intfName2=sp.WAN_INTF,
            bw=bw,
            delay='10ms',
        )

    net.start()

    for key, ip_hub, intf_hub, ip_spoke, bw in WAN:
        sp = spokes[key]
        a1.border_router.setIP(ip_hub, intf=intf_hub)
        sp.gateway.setIP(ip_spoke, intf=sp.WAN_INTF)

    for s in sites:
        s.configure()

    r = a1.border_router

    for key, ip_hub, intf_hub, ip_spoke, bw in WAN:
        sp = spokes[key]
        r.cmd(f'ip route replace 10.{sp.SITE_ID}.0.0/16 via {ip_spoke.split("/")[0]} dev {intf_hub}')
        sp.gateway.cmd(f'ip route replace default via {ip_hub.split("/")[0]} dev {sp.WAN_INTF}')

    harden_rp_filter(net)
    prep_resolv(net)
    write_configs(sites)

    a1.start_services(DHCP_CONF, DNS_CONF)

    for s in sites:
        s.relay_target = a1.dhcp_server_ip
        s.start_relay()

    return net


def main():
    setLogLevel('warning')
    cleanup()

    net = Mininet(
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=False,
    )

    print("== Levantando la red (4 sedes) ...")
    build(net)

    try:
        print("== Esperando servicios base (dnsmasq / web / ftp / relay) ...")
        time.sleep(5)

        ha1_10 = net.get('h-a1-v10')
        ha1_20 = net.get('h-a1-v20')
        ha2 = net.get('h-a2-v40')
        hb1 = net.get('h-b1-v50')
        hb2 = net.get('h-b2-v60')

        test_hosts = [
            (ha1_10, '10.1.10.', '10.1.10.10', '10.1.10.254'),
            (ha1_20, '10.1.20.', '10.1.20.20', '10.1.20.254'),
            (ha2,    '10.2.40.', '10.2.40.40', '10.2.40.254'),
            (hb1,    '10.3.50.', '10.3.50.50', '10.3.50.254'),
            (hb2,    '10.4.60.', '10.4.60.60', '10.4.60.254'),
        ]

        print("== Probando DHCP sin bloquear el test ...")
        for h, prefix, static_ip, gw in test_hosts:
            start_dhcp_probe(h)

        time.sleep(25)

        dhcp_logs = {}
        for h, prefix, static_ip, gw in test_hosts:
            log = read_dhcp_log(h)
            dhcp_logs[h.name] = log
            ip = host_ip(h)
            print(f"  - {h.name}: {ip or 'SIN IP'}")

        # Para las pruebas funcionales, usamos IP fija.
        # Así si DHCP falla, no destruye DNS/Web/FTP/WAN.
        print("== Configurando IPs estaticas para pruebas funcionales ...")
        for h, prefix, static_ip, gw in test_hosts:
            set_static(h, static_ip, gw)
            print(f"  - {h.name}: {host_ip(h)}")

        print("\n[1] DHCP central + relay:")
        check("A1  h-a1-v10 recibio OFFER/ACK para 10.1.10.x",
              dhcp_log_ok(dhcp_logs['h-a1-v10'], '10.1.10.'))
        check("A2  h-a2-v40 recibio OFFER/ACK para 10.2.40.x",
              dhcp_log_ok(dhcp_logs['h-a2-v40'], '10.2.40.'))
        check("B1  h-b1-v50 recibio OFFER/ACK para 10.3.50.x",
              dhcp_log_ok(dhcp_logs['h-b1-v50'], '10.3.50.'))
        check("B2  h-b2-v60 recibio OFFER/ACK para 10.4.60.x",
              dhcp_log_ok(dhcp_logs['h-b2-v60'], '10.4.60.'))

        print("\n[2] Inter-VLAN local (Router-on-a-Stick en A1):")
        check("h-a1-v10 -> gateway de VLAN 20 (10.1.20.254)",
              ping_ok(ha1_10, '10.1.20.254'))
        check("h-a1-v10 -> h-a1-v20",
              ping_ok(ha1_10, '10.1.20.20'))

        print("\n[3] WAN hub-and-spoke:")
        check("A2 -> servidor web en A1 (10.1.100.4)",
              ping_ok(ha2, '10.1.100.4'))
        check("B2 -> servidor web en A1 (10.1.100.4)",
              ping_ok(hb2, '10.1.100.4'))
        check("A2 -> B1 spoke-to-spoke via hub",
              ping_ok(ha2, '10.3.50.50'))

        print("\n[4] DNS interno (dnsmasq):")
        check("dig @10.1.100.3 web.corp.local -> 10.1.100.4",
              '10.1.100.4' in ha2.cmd('dig +short @10.1.100.3 web.corp.local'))
        check("dig web.corp.local -> 10.1.100.4",
              '10.1.100.4' in ha2.cmd('dig +short web.corp.local'))

        print("\n[5] Servidor Web (http.server):")
        check("curl http://10.1.100.4",
              'Datacenter' in ha2.cmd('curl -s --max-time 6 http://10.1.100.4'))
        check("curl http://web.corp.local",
              'Datacenter' in hb2.cmd('curl -s --max-time 6 http://web.corp.local'))

        print("\n[6] Servidor FTP (pyftpdlib):")
        check("curl ftp://admin:***@10.1.100.5/ lista welcome.txt",
              'welcome.txt' in ha2.cmd('curl -s --max-time 6 ftp://admin:secret123@10.1.100.5/'))
        check("curl ftp://admin:***@10.1.100.5/welcome.txt descarga archivo",
              'Archivo de prueba FTP' in ha2.cmd('curl -s --max-time 6 ftp://admin:secret123@10.1.100.5/welcome.txt'))

        print("\n[7] Redundancia del doble nucleo:")
        print("    (informativo: con rutas estaticas el failover depende del kernel)")
        for d in ('r-a1', 'srv-dhcp', 'srv-dns', 'srv-web', 'srv-ftp'):
            net.configLinkStatus(d, 'core1', 'down')

        time.sleep(2)

        info("A2 -> servidor sigue respondiendo via core2",
             ping_ok(ha2, '10.1.100.4'))

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
PY