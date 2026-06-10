#!/bin/bash
# Arranque del contenedor: carga modulos, levanta Open vSwitch y lanza la red.
# Requiere correr con --privileged (lo pone docker-compose.yml).

# Modulos del kernel (mejor esfuerzo: si el host ya los tiene cargados, esto
# no hace falta; el volumen /lib/modules permite cargarlos desde el contenedor)
modprobe openvswitch 2>/dev/null || true
modprobe 8021q 2>/dev/null || true

# Open vSwitch no corre como servicio en un contenedor: lo levantamos a mano
if ! ovs-vsctl show >/dev/null 2>&1; then
    mkdir -p /var/run/openvswitch /etc/openvswitch
    [ -f /etc/openvswitch/conf.db ] || \
        ovsdb-tool create /etc/openvswitch/conf.db \
                   /usr/share/openvswitch/vswitch.ovsschema
    ovsdb-server --remote=punix:/var/run/openvswitch/db.sock \
                 --pidfile --detach >/dev/null 2>&1
    ovs-vsctl --no-wait init
    ovs-vswitchd --pidfile --detach >/dev/null 2>&1
fi

if ! ovs-vsctl show >/dev/null 2>&1; then
    echo "ERROR: Open vSwitch no arranco. ¿Corriste el contenedor con --privileged?" >&2
    exit 1
fi

mn -c >/dev/null 2>&1 || true

case "$1" in
    test)  exec python3 -u test_red.py ;;
    cli|"") exec python3 master_wan.py ;;
    *)     exec "$@" ;;
esac
