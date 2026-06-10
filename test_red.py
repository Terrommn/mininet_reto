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


def find_host(sites, name):
    # busca por el diccionario nombre->host que cada sede llena en build()
    # con el mismo literal que paso a addHost (sin leer atributos de Mininet)
    for s in sites:
        if name in s.hosts_by_name:
            return s.hosts_by_name[name]
    raise KeyError(name)


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


def host_ip(name, host):
    intf = f'{name}-eth0'
    out = host.cmd(f'ip -4 -o addr show {intf}')
    m = re.search(r'inet (10[.][0-9.]+)', out)
    return m.group(1) if m else None


def dhcp_log_ok(log, prefix):
    return (
        f'bound to {prefix}' in log
        or f'DHCPACK of {prefix}' in log
        or f'DHCPOFFER of {prefix}' in log
    )


def start_dhcp_probe(name, host):
    intf = f'{name}-eth0'
    log = f'/tmp/dhcp-{name}.log'

    print(f"  - Probando DHCP en {name} ({intf})...", flush=True)

    host.cmd(f'ip addr flush dev {intf}')
    host.cmd(f'pkill -9 -f "[d]hclient.*{intf}" 2>/dev/null || true')

    host.cmd('mkdir -p /var/lib/dhcp /run')
    host.cmd(f'rm -f /var/lib/dhcp/dhclient-{name}.leases /run/dhclient-{name}.pid {log}')
    host.cmd(f'touch /var/lib/dhcp/dhclient-{name}.leases')
    host.cmd(f'chmod 666 /var/lib/dhcp/dhclient-{name}.leases')

    cmd = dhclient_cmd(name)
    host.cmd(f'(timeout -k 2 -s KILL 20 {cmd}) > {log} 2>&1 &')


def read_dhcp_log(name, host):
    return host.cmd(f'cat /tmp/dhcp-{name}.log 2>/dev/null')


def set_static(name, host, ip, gw):
    intf = f'{name}-eth0'
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
            port1=int(intf_hub.rsplit('eth', 1)[1]),
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

    harden_rp_filter(sites)
    prep_resolv(sites)
    write_configs(sites)

    a1.start_services(DHCP_CONF, DNS_CONF)

    for s in sites:
        s.relay_target = a1.dhcp_server_ip
        s.start_relay()

    return sites


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
    sites = build(net)

    try:
        print("== Esperando servicios base (dnsmasq / web / ftp / relay) ...")
        time.sleep(5)

        ha1_10 = find_host(sites, 'h_a1_v10')
        ha1_20 = find_host(sites, 'h_a1_v20')
        ha2 = find_host(sites, 'h_a2_v40')
        hb1 = find_host(sites, 'h_b1_v50')
        hb2 = find_host(sites, 'h_b2_v60')

        test_hosts = [
            ('h_a1_v10', ha1_10, '10.1.10.', '10.1.10.10', '10.1.10.254'),
            ('h_a1_v20', ha1_20, '10.1.20.', '10.1.20.20', '10.1.20.254'),
            ('h_a2_v40', ha2,    '10.2.40.', '10.2.40.40', '10.2.40.254'),
            ('h_b1_v50', hb1,    '10.3.50.', '10.3.50.50', '10.3.50.254'),
            ('h_b2_v60', hb2,    '10.4.60.', '10.4.60.60', '10.4.60.254'),
        ]

        print("== Probando DHCP sin bloquear el test ...")
        for name, h, prefix, static_ip, gw in test_hosts:
            start_dhcp_probe(name, h)

        time.sleep(25)

        dhcp_logs = {}
        for name, h, prefix, static_ip, gw in test_hosts:
            log = read_dhcp_log(name, h)
            dhcp_logs[name] = log
            ip = host_ip(name, h)
            print(f"  - {name}: {ip or 'SIN IP'}")

        # Para las pruebas funcionales, usamos IP fija.
        # Así si DHCP falla, no destruye DNS/Web/FTP/WAN.
        print("== Configurando IPs estaticas para pruebas funcionales ...")
        for name, h, prefix, static_ip, gw in test_hosts:
            set_static(name, h, static_ip, gw)
            print(f"  - {name}: {host_ip(name, h)}")

        print("\n[1] DHCP central + relay:")
        check("A1  h_a1_v10 recibio OFFER/ACK para 10.1.10.x",
              dhcp_log_ok(dhcp_logs['h_a1_v10'], '10.1.10.'))
        check("A2  h_a2_v40 recibio OFFER/ACK para 10.2.40.x",
              dhcp_log_ok(dhcp_logs['h_a2_v40'], '10.2.40.'))
        check("B1  h_b1_v50 recibio OFFER/ACK para 10.3.50.x",
              dhcp_log_ok(dhcp_logs['h_b1_v50'], '10.3.50.'))
        check("B2  h_b2_v60 recibio OFFER/ACK para 10.4.60.x",
              dhcp_log_ok(dhcp_logs['h_b2_v60'], '10.4.60.'))

        print("\n[2] Inter-VLAN local (Router-on-a-Stick en A1):")
        check("h_a1_v10 -> gateway de VLAN 20 (10.1.20.254)",
              ping_ok(ha1_10, '10.1.20.254'))
        check("h_a1_v10 -> h_a1_v20",
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
        a1 = sites[0]
        core1 = a1.core1
        # Ambos extremos de cada enlace hacia core1 (equivale a 'link X core1 down' de s7)
        core1_links = [
            (a1.border_router, 'r_a1-eth1', 'core1-eth0'),
            (a1.srv_dhcp, 'srv_dhcp-eth0', 'core1-eth2'),
            (a1.srv_dns, 'srv_dns-eth0', 'core1-eth3'),
            (a1.srv_web, 'srv_web-eth0', 'core1-eth4'),
            (a1.srv_ftp, 'srv_ftp-eth0', 'core1-eth5'),
        ]
        for node, near, far in core1_links:
            node.cmd(f'ip link set {near} down')
            core1.cmd(f'ip link set {far} down')

        time.sleep(2)

        info("A2 -> servidor sigue respondiendo via core2",
             ping_ok(ha2, '10.1.100.4'))

        for node, near, far in core1_links:
            node.cmd(f'ip link set {near} up')
            core1.cmd(f'ip link set {far} up')

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