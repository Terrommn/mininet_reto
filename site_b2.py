#!/usr/bin/env python3
from common_router import Router


class SiteB2:
    SITE_ID = 4
    PREFIX = '10.4'
    ROUTER = 'r_b2'
    SWITCH = 'sw_b2'
    HOST = 'h_b2_v'
    WAN_INTF = 'r_b2-eth1'
    TRUNK = 'sw_b2-eth20'
    VLANS = [50, 60, 110, 120, 130, 140, 99]

    def __init__(self):
        self.gateway = None
        self.switch = None
        self.subifs = []
        self.relay_target = None
        self.user_hosts = []
        # nombre (el literal pasado a addHost) -> objeto host: permite ubicar
        # hosts por nombre sin leer atributos de Mininet fuera de los labs
        self.hosts_by_name = {}

    def build(self, net):
        self.gateway = net.addHost(self.ROUTER, cls=Router, ip=None)
        self.switch = net.addSwitch(self.SWITCH, failMode='standalone')
        for i, vid in enumerate(self.VLANS, start=1):
            name = f'{self.HOST}{vid}'
            h = net.addHost(name, ip=None, privateDirs=['/etc'])
            self.user_hosts.append(h)
            self.hosts_by_name[name] = h
            net.addLink(h, self.switch, intfName2=f'{self.SWITCH}-eth{i}')
        net.addLink(self.switch, self.gateway,
                    port1=20, intfName2=f'{self.ROUTER}-eth0')

    def rp_intfs(self):
        return [(self.gateway, f'{self.ROUTER}-eth0'),
                (self.gateway, self.WAN_INTF)]

    def configure(self):
        r, sw = self.gateway, self.switch
        trunk_list = ','.join(str(v) for v in self.VLANS)
        for i, vid in enumerate(self.VLANS, start=1):
            sw.cmd(f'ovs-vsctl set port {self.SWITCH}-eth{i} tag={vid}')
        sw.cmd(f'ovs-vsctl set port {self.TRUNK} trunks={trunk_list}')
        for vid in self.VLANS:
            sub = f'{self.ROUTER}-eth0.{vid}'
            r.cmd(f'ip link add link {self.ROUTER}-eth0 name {sub} type vlan id {vid}')
            r.cmd(f'ip addr add {self.PREFIX}.{vid}.254/24 dev {sub}')
            r.cmd(f'ip link set up {sub}')
            self.subifs.append(sub)
        r.cmd(f'ip link set up {self.ROUTER}-eth0')

    def start_relay(self):
        ifaces = self.subifs + [self.WAN_INTF]
        opt = ' '.join(f'-i {i}' for i in ifaces)
        self.gateway.cmd(f'dhcrelay -4 {opt} {self.relay_target}')
