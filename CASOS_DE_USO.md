# Casos de uso — Demo en vivo (Red Peeda + Vuul)

Guion de demostración: cada caso es una situación real de la empresa fusionada,
con los comandos listos para copiar/pegar. Arranca la red y todos los comandos
se escriben en el prompt `mininet>`:

```bash
docker compose run --rm red
```

> Sintaxis: `nodo comando` se ejecuta en ese nodo. La CLI sustituye nombres de host
> por su IP actual (por eso funciona `ping h_b1_v50` aunque la IP venga de DHCP).

---

### Caso 1 — Se conecta una laptop nueva en CDMX · **DHCP (DORA) + relay**

*Un operador nuevo en CDMX enciende su equipo: recibe IP del servidor central de
Monterrey, cruzando la WAN gracias al `dhcrelay` (giaddr).*

```text
mininet> h_b2_v60 dhclient -v -1 -lf /var/lib/dhcp/dhclient-h_b2_v60.leases -pf /run/dhclient-h_b2_v60.pid h_b2_v60-eth0
mininet> h_b2_v60 ip -4 addr show h_b2_v60-eth0
mininet> srv_dhcp grep -E "DISCOVER|OFFER|REQUEST|ACK" /tmp/dhcp_corp.log | tail -n 8
```

**Esperado:** `dhclient` imprime el DORA y el host queda con IP `10.4.60.50–150`;
el log del servidor muestra el mismo intercambio para esa IP.

**Preparación del resto de la demo** — repite para los demás actores (con `-nw` no bloquea;
espera ~10 s al terminar):

```text
mininet> h_a1_v10 dhclient -nw -1 -lf /var/lib/dhcp/dhclient-h_a1_v10.leases -pf /run/dhclient-h_a1_v10.pid h_a1_v10-eth0
mininet> h_a1_v20 dhclient -nw -1 -lf /var/lib/dhcp/dhclient-h_a1_v20.leases -pf /run/dhclient-h_a1_v20.pid h_a1_v20-eth0
mininet> h_a2_v40 dhclient -nw -1 -lf /var/lib/dhcp/dhclient-h_a2_v40.leases -pf /run/dhclient-h_a2_v40.pid h_a2_v40-eth0
mininet> h_b1_v50 dhclient -nw -1 -lf /var/lib/dhcp/dhclient-h_b1_v50.leases -pf /run/dhclient-h_b1_v50.pid h_b1_v50-eth0
mininet> h_b1_v70 dhclient -nw -1 -lf /var/lib/dhcp/dhclient-h_b1_v70.leases -pf /run/dhclient-h_b1_v70.pid h_b1_v70-eth0
```

### Caso 2 — El empleado abre la intranet por nombre, no por IP · **DNS**

*Nadie memoriza IPs: el DNS interno (dnsmasq en el data center) resuelve `*.corp.local`.*

```text
mininet> h_b2_v60 dig +short web.corp.local
mininet> h_b2_v60 dig @10.1.100.3 +short ftp.corp.local
```

**Esperado:** `10.1.100.4` y `10.1.100.5`. (Sin `@` usa el DNS que llegó por DHCP.)

### Caso 3 — Consultar la intranet corporativa desde una sucursal · **HTTP**

*Desde CDMX se consulta el portal interno alojado en Monterrey: DNS + ruteo WAN + web.*

```text
mininet> h_b2_v60 curl -s http://web.corp.local
```

**Esperado:** `<h1>Datacenter A1 - Peeda+Vuul (web.corp.local)</h1>`

### Caso 4 — Finanzas comparte la nómina con el corporativo · **FTP**

*Finanzas (Querétaro) descarga una plantilla del servidor central y sube su reporte:
ya no se mandan archivos por correo como antes de la fusión.*

```text
mininet> h_b1_v70 curl -s ftp://admin:secret123@10.1.100.5/welcome.txt
mininet> h_b1_v70 echo "Nomina Q2 - Finanzas QRO" > /tmp/nomina_q2.txt
mininet> h_b1_v70 curl -s -T /tmp/nomina_q2.txt ftp://admin:secret123@ftp.corp.local/
mininet> srv_ftp ls /tmp/ftp_share
```

**Esperado:** descarga `Archivo de prueba FTP - Peeda+Vuul`; el `ls` del servidor
ya incluye `nomina_q2.txt`.

### Caso 5 — Dirección consulta a TI dentro de Monterrey · **802.1Q + inter-VLAN (RoaS)**

*Dirección (VLAN 10) y TI (VLAN 20) están en segmentos separados del mismo switch;
se comunican solo a través del router (Router-on-a-Stick).*

```text
mininet> h_a1_v10 ping -c2 h_a1_v20
mininet> r_a1 ip -d link show r_a1-eth0.10
```

**Esperado:** 0% loss con `ttl=63` (pasó por un router); la subinterfaz muestra
`vlan protocol 802.1Q id 10`.

### Caso 6 — Ventas GDL colabora con Operaciones QRO · **WAN hub-and-spoke (rutas estáticas)**

*No hay enlace directo GDL–QRO: el tráfico transita por el hub de Monterrey.
Lo demostramos capturando en la interfaz WAN del hub hacia Querétaro.*

```text
mininet> r_a1 tcpdump -ni r_a1-eth4 -c 6 icmp > /tmp/transito_wan.txt 2>&1 &
mininet> h_a2_v40 ping -c3 h_b1_v50
mininet> r_a1 cat /tmp/transito_wan.txt
```

**Esperado:** 0% loss (`ttl=61`: 3 saltos) y la captura muestra los echo `10.2.40.x > 10.3.50.x`
atravesando el hub — 6 paquetes capturados.

### Caso 7 — Falla el núcleo 1 y la intranet sigue en línea · **Redundancia (ECMP + dual-homing)**

*Mantenimiento o falla del core 1 del data center: el servicio continúa por el core 2.*

```text
mininet> h_a2_v40 ping -c2 10.1.100.4
mininet> link r_a1 core1 down
mininet> link srv_web core1 down
mininet> h_a2_v40 ping -c3 10.1.100.4
mininet> link r_a1 core1 up
mininet> link srv_web core1 up
```

**Esperado:** el segundo ping sigue con 0% loss — el tráfico se fue por `core2`.

### Caso 8 — CDMX contrató 20 Mbps para el ERP; GDL solo 10 · **Capacidad WAN (TCLink)**

*Medimos el ancho de banda real de cada enlace dedicado contra el data center.*

```text
mininet> srv_web iperf -s &
mininet> h_a2_v40 iperf -c 10.1.100.4 -t 5
mininet> h_b2_v60 iperf -c 10.1.100.4 -t 5
mininet> srv_web pkill -f "iperf -s"
```

**Esperado:** GDL ≈ `9.6 Mbits/sec` (enlace de 10) y CDMX ≈ `19 Mbits/sec` (enlace de 20):
cada sucursal obtiene exactamente la tasa contratada.

---

**Cierre:** `mininet> exit`. Para validar todo de un golpe sin demo manual:
`docker compose run --rm red test` (esperado: `15/15 pruebas OK`).
