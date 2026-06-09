from common_router import Router


class SiteB1:
    SITE_ID = 3
    PREFIX = '10.3'
    ROUTER = 'r-b1'
    SWITCH = 'sw-b1'
    HOST = 'h-b1-v'
    WAN_INTF = 'r-b1-eth1'
    TRUNK = 'sw-b1-eth20'
    VLANS = [50, 60, 70, 80, 110, 120, 130, 140, 99]

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
        net.addLink(self.switch, self.gateway,
                    intfName1=self.TRUNK, intfName2=f'{self.ROUTER}-eth0')

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
