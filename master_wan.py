from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from common_router import Router
from site_a1 import SiteA1
from site_a2 import SiteA2
from site_b1 import SiteB1
from site_b2 import SiteB2

DHCP_CONF = '/tmp/dhcp_corp.conf'
DNS_CONF = '/tmp/dns_corp.conf'
DNS_ZONE = '/tmp/corp_dns.txt'
WAN = [
    ('a2', '10.99.1.1/30', 'r-a1-eth3', '10.99.1.2/30', 10),
    ('b1', '10.99.2.1/30', 'r-a1-eth4', '10.99.2.2/30', 10),
    ('b2', '10.99.3.1/30', 'r-a1-eth5', '10.99.3.2/30', 20),
]


def write_configs(sites):
    lines = ['except-interface=lo', 'port=0']
    for s in sites:
        for vid in s.VLANS:
            tag = f's{s.SITE_ID}v{vid}'
            base = f'10.{s.SITE_ID}.{vid}'
            lines.append(f'dhcp-range=set:{tag},{base}.50,{base}.150,255.255.255.0,12h')
            lines.append(f'dhcp-option=tag:{tag},option:router,{base}.254')
            lines.append(f'dhcp-option=tag:{tag},option:dns-server,10.1.100.3')
    with open(DHCP_CONF, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    with open(DNS_ZONE, 'w') as f:
        f.write('10.1.100.3 dns.corp.local\n'
                '10.1.100.4 web.corp.local\n'
                '10.1.100.2 dhcp.corp.local\n'
                '10.1.100.5 ftp.corp.local\n')
    with open(DNS_CONF, 'w') as f:
        f.write(f'no-hosts\nno-resolv\nlog-queries\naddn-hosts={DNS_ZONE}\n')


def main():
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink,
                  autoSetMacs=True, autoStaticArp=False)
    a1, a2, b1, b2 = SiteA1(), SiteA2(), SiteB1(), SiteB2()
    sites = [a1, a2, b1, b2]
    spokes = {'a2': a2, 'b1': b1, 'b2': b2}
    for s in sites:
        s.build(net)
    for key, ip_hub, intf_hub, ip_spoke, bw in WAN:
        sp = spokes[key]
        net.addLink(a1.border_router, sp.gateway,
                    intfName1=intf_hub, intfName2=sp.WAN_INTF, bw=bw, delay='10ms')
    net.start()
    for key, ip_hub, intf_hub, ip_spoke, bw in WAN:
        a1.border_router.setIP(ip_hub, intf=intf_hub)
        spokes[key].gateway.setIP(ip_spoke, intf=spokes[key].WAN_INTF)
    for s in sites:
        s.configure()
    r = a1.border_router
    r.cmd('ip route replace 10.2.0.0/16 via 10.99.1.2 dev r-a1-eth3')
    r.cmd('ip route replace 10.3.0.0/16 via 10.99.2.2 dev r-a1-eth4')
    r.cmd('ip route replace 10.4.0.0/16 via 10.99.3.2 dev r-a1-eth5')
    a2.gateway.cmd('ip route replace default via 10.99.1.1 dev r-a2-eth1')
    b1.gateway.cmd('ip route replace default via 10.99.2.1 dev r-b1-eth1')
    b2.gateway.cmd('ip route replace default via 10.99.3.1 dev r-b2-eth1')
    write_configs(sites)
    a1.start_services(DHCP_CONF, DNS_CONF)
    for s in sites:
        s.relay_target = a1.dhcp_server_ip
        s.start_relay()
    info('\n*** Red Peeda+Vuul lista (hub A1 + spokes A2/B1/B2). Pruebas en README.md\n\n')
    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    main()
