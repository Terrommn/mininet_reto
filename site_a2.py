#!/usr/bin/env python3
# sede a2 guadalajara (spoke) - router-on-a-stick
from common_router import Router


class SiteA2:
    SITE_ID = 2
    PREFIX = '10.2'
    ROUTER = 'r-a2'
    SWITCH = 'sw-a2'
    HOST = 'h-a2-v'
    WAN_INTF = 'r-a2-eth1'
    TRUNK = 'sw-a2-eth20'
    VLANS = [40, 30, 110, 120, 130, 140, 99]

    def __init__(self):
        self.gateway = None
        self.switch = None
        self.subifs = []
        self.relay_target = None

    def build(self, net):
        self.gateway = net.addHost(self.ROUTER, cls=Router, ip=None)
        self.switch = net.addSwitch(self.SWITCH, failMode='standalone')
        for i, vid in enumerate(self.VLANS, start=1):
            h = net.addHost(f'{self.HOST}{vid}', ip=None, privateDirs=['/etc'])
            net.addLink(h, self.switch, intfName2=f'{self.SWITCH}-eth{i}')
        # trunk hacia el router
        net.addLink(self.switch, self.gateway,
                    intfName1=self.TRUNK, intfName2=f'{self.ROUTER}-eth0')

    def configure(self):
        r, sw = self.gateway, self.switch
        trunk_list = ','.join(str(v) for v in self.VLANS)
        
        # tags de vlan en el switch
        for i, vid in enumerate(self.VLANS, start=1):
            sw.cmd(f'ovs-vsctl set port {self.SWITCH}-eth{i} tag={vid}')
        sw.cmd(f'ovs-vsctl set port {self.TRUNK} trunks={trunk_list}')
        
        
        # subinterfaces = gateways .254
        for vid in self.VLANS:
            sub = f'{self.ROUTER}-eth0.{vid}'
            r.cmd(f'ip link add link {self.ROUTER}-eth0 name {sub} type vlan id {vid}')
            r.cmd(f'ip addr add {self.PREFIX}.{vid}.254/24 dev {sub}')
            r.cmd(f'ip link set up {sub}')
            self.subifs.append(sub)
        r.cmd(f'ip link set up {self.ROUTER}-eth0')

    def start_relay(self):
        # escuchar en las vlans y en el wan para el offer de vuelta
        ifaces = self.subifs + [self.WAN_INTF]
        opt = ' '.join(f'-i {i}' for i in ifaces)
        self.gateway.cmd(f'dhcrelay -4 {opt} {self.relay_target}')
