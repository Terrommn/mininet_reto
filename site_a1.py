#!/usr/bin/env python3
from common_router import Router


class SiteA1:
    SITE_ID = 1
    PREFIX = '10.1'
    VLANS = [10, 20, 30, 40, 80, 99, 110, 120, 130, 140]

    def __init__(self):
        self.border_router = None
        self.core1 = None
        self.core2 = None
        self.srv_dhcp = None
        self.srv_dns = None
        self.srv_web = None
        self.srv_ftp = None
        self.switch = None
        self.subifs = []
        self.relay_target = None
        self.dhcp_server_ip = '10.1.100.2'
        self.dns_server_ip = '10.1.100.3'
        self.web_server_ip = '10.1.100.4'
        self.ftp_server_ip = '10.1.100.5'
        self.user_subnet = '10.1.0.0/16'
        self.user_hosts = []
        # nombre (el literal pasado a addHost) -> objeto host: permite ubicar
        # hosts por nombre sin leer atributos de Mininet fuera de los labs
        self.hosts_by_name = {}

    def build(self, net):
        r = net.addHost('r_a1', cls=Router, ip=None); self.border_router = r
        c1 = net.addHost('core1', cls=Router, ip=None); self.core1 = c1
        c2 = net.addHost('core2', cls=Router, ip=None); self.core2 = c2
        sd = net.addHost('srv_dhcp', cls=Router, ip=None); self.srv_dhcp = sd
        sn = net.addHost('srv_dns', cls=Router, ip=None); self.srv_dns = sn
        sw = net.addHost('srv_web', cls=Router, ip=None); self.srv_web = sw
        sf = net.addHost('srv_ftp', cls=Router, ip=None); self.srv_ftp = sf
        acc = net.addSwitch('sw_a1', failMode='standalone'); self.switch = acc
        for i, vid in enumerate(self.VLANS, start=1):
            name = f'h_a1_v{vid}'
            h = net.addHost(name, ip=None, privateDirs=['/etc'])
            self.user_hosts.append(h)
            self.hosts_by_name[name] = h
            net.addLink(h, acc, intfName2=f'sw_a1-eth{i}')
        net.addLink(acc, r, port1=20, intfName2='r_a1-eth0')
        net.addLink(r, c1, port1=1, intfName2='core1-eth0')
        net.addLink(r, c2, port1=2, intfName2='core2-eth0')
        net.addLink(c1, c2, port1=1, intfName2='core2-eth1')
        net.addLink(sd, c1, port1=0, intfName2='core1-eth2')
        net.addLink(sd, c2, port1=1, intfName2='core2-eth2')
        net.addLink(sn, c1, port1=0, intfName2='core1-eth3')
        net.addLink(sn, c2, port1=1, intfName2='core2-eth3')
        net.addLink(sw, c1, port1=0, intfName2='core1-eth4')
        net.addLink(sw, c2, port1=1, intfName2='core2-eth4')
        net.addLink(sf, c1, port1=0, intfName2='core1-eth5')
        net.addLink(sf, c2, port1=1, intfName2='core2-eth5')

    def rp_intfs(self):
        intfs = [(self.border_router, f'r_a1-eth{n}') for n in range(6)]
        intfs += [(self.core1, f'core1-eth{n}') for n in range(6)]
        intfs += [(self.core2, f'core2-eth{n}') for n in range(6)]
        servers = [(self.srv_dhcp, 'srv_dhcp'), (self.srv_dns, 'srv_dns'),
                   (self.srv_web, 'srv_web'), (self.srv_ftp, 'srv_ftp')]
        for node, base in servers:
            intfs += [(node, f'{base}-eth0'), (node, f'{base}-eth1')]
        return intfs

    def configure(self):
        r, c1, c2 = self.border_router, self.core1, self.core2
        sd, sn, sw, sf, acc = (self.srv_dhcp, self.srv_dns, self.srv_web,
                               self.srv_ftp, self.switch)
        trunk_list = ','.join(str(v) for v in self.VLANS)
        for i, vid in enumerate(self.VLANS, start=1):
            acc.cmd(f'ovs-vsctl set port sw_a1-eth{i} tag={vid}')
        acc.cmd(f'ovs-vsctl set port sw_a1-eth20 trunks={trunk_list}')
        for vid in self.VLANS:
            sub = f'r_a1-eth0.{vid}'
            r.cmd(f'ip link add link r_a1-eth0 name {sub} type vlan id {vid}')
            r.cmd(f'ip addr add 10.1.{vid}.254/24 dev {sub}')
            r.cmd(f'ip link set up {sub}')
            self.subifs.append(sub)
        r.cmd('ip link set up r_a1-eth0')
        r.setIP('172.16.0.1/30', intf='r_a1-eth1')
        r.setIP('172.16.0.5/30', intf='r_a1-eth2')
        c1.setIP('172.16.0.2/30', intf='core1-eth0')
        c1.setIP('172.16.0.9/30', intf='core1-eth1')
        c1.setIP('172.16.1.1/30', intf='core1-eth2')
        c1.setIP('172.16.2.1/30', intf='core1-eth3')
        c1.setIP('172.16.3.1/30', intf='core1-eth4')
        c1.setIP('172.16.4.1/30', intf='core1-eth5')
        c2.setIP('172.16.0.6/30', intf='core2-eth0')
        c2.setIP('172.16.0.10/30', intf='core2-eth1')
        c2.setIP('172.16.1.5/30', intf='core2-eth2')
        c2.setIP('172.16.2.5/30', intf='core2-eth3')
        c2.setIP('172.16.3.5/30', intf='core2-eth4')
        c2.setIP('172.16.4.5/30', intf='core2-eth5')
        sd.setIP('172.16.1.2/30', intf='srv_dhcp-eth0')
        sd.setIP('172.16.1.6/30', intf='srv_dhcp-eth1')
        sn.setIP('172.16.2.2/30', intf='srv_dns-eth0')
        sn.setIP('172.16.2.6/30', intf='srv_dns-eth1')
        sw.setIP('172.16.3.2/30', intf='srv_web-eth0')
        sw.setIP('172.16.3.6/30', intf='srv_web-eth1')
        sf.setIP('172.16.4.2/30', intf='srv_ftp-eth0')
        sf.setIP('172.16.4.6/30', intf='srv_ftp-eth1')
        sd.cmd('ip addr add 10.1.100.2/32 dev lo')
        sn.cmd('ip addr add 10.1.100.3/32 dev lo')
        sw.cmd('ip addr add 10.1.100.4/32 dev lo')
        sf.cmd('ip addr add 10.1.100.5/32 dev lo')
        r.cmd('ip route replace 10.1.100.0/24 '
              'nexthop via 172.16.0.2 dev r_a1-eth1 '
              'nexthop via 172.16.0.6 dev r_a1-eth2')
        c1.cmd('ip route replace default via 172.16.0.1 dev core1-eth0')
        c1.cmd('ip route replace 10.1.100.2/32 via 172.16.1.2 dev core1-eth2')
        c1.cmd('ip route replace 10.1.100.3/32 via 172.16.2.2 dev core1-eth3')
        c1.cmd('ip route replace 10.1.100.4/32 via 172.16.3.2 dev core1-eth4')
        c1.cmd('ip route replace 10.1.100.5/32 via 172.16.4.2 dev core1-eth5')
        c2.cmd('ip route replace default via 172.16.0.5 dev core2-eth0')
        c2.cmd('ip route replace 10.1.100.2/32 via 172.16.1.6 dev core2-eth2')
        c2.cmd('ip route replace 10.1.100.3/32 via 172.16.2.6 dev core2-eth3')
        c2.cmd('ip route replace 10.1.100.4/32 via 172.16.3.6 dev core2-eth4')
        c2.cmd('ip route replace 10.1.100.5/32 via 172.16.4.6 dev core2-eth5')
        sd.cmd('ip route replace default '
               'nexthop via 172.16.1.1 dev srv_dhcp-eth0 '
               'nexthop via 172.16.1.5 dev srv_dhcp-eth1')
        sn.cmd('ip route replace default '
               'nexthop via 172.16.2.1 dev srv_dns-eth0 '
               'nexthop via 172.16.2.5 dev srv_dns-eth1')
        sw.cmd('ip route replace default '
               'nexthop via 172.16.3.1 dev srv_web-eth0 '
               'nexthop via 172.16.3.5 dev srv_web-eth1')
        sf.cmd('ip route replace default '
               'nexthop via 172.16.4.1 dev srv_ftp-eth0 '
               'nexthop via 172.16.4.5 dev srv_ftp-eth1')

    def start_services(self, dhcp_conf, dns_conf):
        self.srv_dns.cmd(f'dnsmasq --conf-file={dns_conf} --pid-file=/tmp/dns_corp.pid')
        self.srv_dhcp.cmd(f'dnsmasq --conf-file={dhcp_conf} --pid-file=/tmp/dhcp_corp.pid --dhcp-leasefile=/tmp/dhcp_corp.leases --log-dhcp --log-facility=/tmp/dhcp_corp.log')
        self.srv_web.cmd('mkdir -p /tmp/web && echo "<h1>Datacenter A1 - Peeda+Vuul (web.corp.local)</h1>" > /tmp/web/index.html')
        self.srv_web.cmd('cd /tmp/web && python3 -m http.server 80 > /tmp/web/http.log 2>&1 &')
        self.srv_ftp.cmd('mkdir -p /tmp/ftp_share && echo "Archivo de prueba FTP - Peeda+Vuul" > /tmp/ftp_share/welcome.txt')
        self.srv_ftp.cmd('cd /tmp/ftp_share && python3 -m pyftpdlib -i 0.0.0.0 -p 21 -w -u admin -P secret123 > /tmp/ftp_share/ftp.log 2>&1 &')

    def start_relay(self):
        ifaces = self.subifs + ['r_a1-eth1', 'r_a1-eth2']
        opt = ' '.join(f'-i {i}' for i in ifaces)
        self.border_router.cmd(f'dhcrelay -4 {opt} {self.relay_target}')
