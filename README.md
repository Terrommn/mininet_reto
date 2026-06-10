# Emulación Mininet — Red post-fusión Peeda + Vuul

Emulación en Mininet de la red corporativa **hub-and-spoke** del Proyecto Integrador
(TC2006B, ITESM). Implementa, usando **solo técnicas vistas en clase** (prácticas
s2/s3/s7/s8/s9): segmentación por VLANs, **Router-on-a-Stick** (s3), **WAN multi-sede
con rutas estáticas/ECMP** (s7), **doble núcleo** con servidores **dual-homed** (s7),
**DHCP central con relay** (s8) y servicios **DNS/Web/FTP** (s8/s9).

---

## 1. Arquitectura

```
                                INTERNET (no emulado)
                                       |
   [A1 - MONTERREY  HUB  10.1.0.0/16]  |
     hosts VLAN(10,20,30,40,80,99,110,120,130,140)
            |  (trunk 802.1Q)
          R-A1 (Router-on-a-Stick + borde WAN + dhcrelay)
          /   \  uplinks /30 (172.16.0.x)
      core1   core2   (doble núcleo, ECMP - patrón s7)
        \\     //   dual-homing /30 (172.16.1-4.x)
        SERVER FARM (VLAN 100, IP de servicio en loopback):
        srv_dhcp 10.1.100.2 · srv_dns 10.1.100.3 · srv_web 10.1.100.4 · srv_ftp 10.1.100.5
            |              |              |
   WAN /30 |  10.99.1.0/30 | 10.99.2.0/30 | 10.99.3.0/30
            |              |              |
        R-A2 (GDL)     R-B1 (QRO)     R-B2 (CDMX)      <- spokes (Router-on-a-Stick)
        10.2.0.0/16    10.3.0.0/16    10.4.0.0/16
```

**Sedes, VLANs y servidores**

| Sede | Rol | Subred | VLANs (1 host c/u) |
|---|---|---|---|
| **A1** Monterrey | HUB | `10.1.0.0/16` | 10 Dir, 20 TI, 30 Admin, 40 Ventas, 80 RH, 99 Mgmt, 110 Imp, 120 Voz, 130 WiFi-Corp, 140 WiFi-Inv, **100 Servidores** |
| **A2** Guadalajara | Spoke | `10.2.0.0/16` | 40, 30, 110, 120, 130, 140, 99 |
| **B1** Querétaro | Spoke | `10.3.0.0/16` | 50 Oper, 60 At.Cliente, 70 Fin, 80 RH, 110, 120, 130, 140, 99 |
| **B2** CDMX | Spoke | `10.4.0.0/16` | 50, 60, 110, 120, 130, 140, 99 |

- **Direccionamiento:** `10.{sede}.{vlan}.0/24`, gateway `.254`, pool DHCP `.50–.150`.
- **WAN /30:** MTY–GDL `10.99.1.0/30` (10 Mbps) · MTY–QRO `10.99.2.0/30` (10 Mbps) · MTY–CDMX `10.99.3.0/30` (20 Mbps).
- **Servicios (4) centralizados en A1**, FQDNs internos `*.corp.local`:

| Servicio | Host | IP servicio | FQDN | Notas |
|---|---|---|---|---|
| DHCP | srv_dhcp | 10.1.100.2 | dhcp.corp.local | dnsmasq + relay multi-sede |
| DNS | srv_dns | 10.1.100.3 | dns.corp.local | dnsmasq (zona interna) |
| Web | srv_web | 10.1.100.4 | web.corp.local | `http.server` :80 |
| FTP | srv_ftp | 10.1.100.5 | ftp.corp.local | pyftpdlib :21 · user `admin` / pass `secret123` |

**Nombres de nodos:** routers `r_a1/r_a2/r_b1/r_b2`, núcleo `core1/core2`, servidores
`srv_dhcp/srv_dns/srv_web/srv_ftp`, hosts de usuario `h_{sede}_v{vlan}` (p. ej.
`h_a1_v10`, `h_a2_v40`, `h_b1_v50`, `h_b2_v60`). La interfaz de cada host es `<host>-eth0`.

---

## 2. Requisitos

> **Atajo: con Docker no instalas nada.** Si tienes Docker, salta a la
> sección **2.1** y olvídate de las dependencias.

Linux (Ubuntu recomendado) con **root/sudo**. Instala las dependencias:

```bash
sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch dnsmasq isc-dhcp-relay \
                        dnsutils curl python3 python3-pyftpdlib
# (alternativa para pyftpdlib si no está en apt:  pip3 install pyftpdlib)
```

> `dnsmasq`, `dhcrelay` (isc-dhcp-relay), `dig` (dnsutils), `curl` y `pyftpdlib`
> son necesarios para los servicios. Si falta `pyftpdlib`, todo funciona salvo el FTP
> (el error quedaría en `/tmp/ftp_share/ftp.log`).

**Archivos del proyecto** (todos en esta carpeta):

| Archivo | Contenido |
|---|---|
| `common_router.py` | Clase `Router` compartida (ip_forward, rp_filter, 8021q) |
| `site_a1.py` | HUB Monterrey (RoaS + doble núcleo ECMP + server farm + servicios) |
| `site_a2.py` `site_b1.py` `site_b2.py` | Spokes (Router-on-a-Stick) |
| `master_wan.py` | Integrador: 1 sola red Mininet, WAN, rutas, servicios, CLI |

---

### 2.1 Alternativa recomendada: Docker (cero instalación)

La imagen trae **todo** (mininet, OVS, dnsmasq, dhcrelay, pyftpdlib...). Solo
necesitas Docker en Linux (o Docker Desktop con backend WSL2 en Windows):

```bash
docker compose build                  # construir la imagen (una sola vez)
docker compose run --rm red test      # correr el test automatico (espera 15/15 OK)
docker compose run --rm red           # abrir la CLI de Mininet (mininet>)
```

Sin compose, equivale a:

```bash
docker build -t mininet-reto .
docker run -it --rm --privileged -v /lib/modules:/lib/modules:ro mininet-reto       # CLI
docker run     --rm --privileged -v /lib/modules:/lib/modules:ro mininet-reto test  # test
```

Notas:
- El contenedor corre **privilegiado** porque Mininet crea namespaces e
  interfaces de red; toda la red vive *dentro* del contenedor (no toca tu red).
- El volumen `/lib/modules` permite cargar los módulos `openvswitch` y `8021q`
  del kernel anfitrión. En la mayoría de los kernels de Ubuntu/WSL2 ya vienen.
- El aviso `Error setting resource limits` al arrancar es inofensivo.
- Dentro de la CLI todo funciona igual que en la sección 4 (pruebas paso a paso).

## 3. Ejecutar

```bash
sudo mn -c                       # limpia restos de cualquier corrida previa
sudo python3 master_wan.py       # levanta la red y abre la CLI de Mininet (mininet>)
```

Al terminar verás el prompt `mininet>`. **Todos los comandos de prueba siguientes se
escriben en ese prompt.** Para salir: `exit` (al final hace `net.stop()` automático).

> Convención de la CLI: `nodo comando` ejecuta en ese nodo (ej. `h_a1_v10 ip a`);
> `sh comando` ejecuta en el host raíz (ej. `sh ovs-vsctl show`).

---

## 4. Pruebas paso a paso

### 4.0 — Verificar que la red levantó

```text
mininet> nodes
mininet> dump
```
**Esperado:** aparecen los 4 routers, `core1/core2`, los 4 `srv_*`, los switches
`sw_a1/sw_a2/sw_b1/sw_b2` y todos los hosts `h_*`.

### 4.1 — Inter-VLAN local (Router-on-a-Stick, s3)

Los gateways `.254` existen desde el arranque (no dependen de DHCP):

```text
mininet> h_a1_v10 ping -c2 10.1.10.254      # su propio gateway
mininet> r_a2 ping -c2 10.2.40.254          # gateway local del spoke
```
**Esperado:** 0% packet loss. (Confirma subinterfaces 802.1Q + tags OVS.)

### 4.2 — WAN hub-and-spoke (rutas estáticas, s7)

```text
mininet> r_a2 ping -c2 10.99.1.1            # spoke -> HUB por el enlace /30
mininet> r_b1 ping -c2 10.1.100.4           # spoke -> servidor en A1 (vía HUB)
mininet> r_a2 ping -c2 10.3.50.254          # spoke A2 -> gateway en spoke B1 (tránsito por HUB)
```
**Esperado:** 0% loss. (Confirma WAN + tránsito spoke↔spoke por el hub.)

### 4.3 — DHCP central con relay multi-sede (s8) ⭐

Primero un host concreto, para ver el proceso DORA:

```text
mininet> h_b1_v50 dhclient -v -1 -lf /var/lib/dhcp/dhclient-h_b1_v50.leases -pf /run/dhclient-h_b1_v50.pid h_b1_v50-eth0
mininet> h_b1_v50 ip -4 addr show h_b1_v50-eth0
```
**Esperado:** el host obtiene una IP en `10.3.50.50–10.3.50.150` y gateway `10.3.50.254`.
Revisa el log del servidor (DISCOVER/OFFER/REQUEST/ACK con el `giaddr` de la subred):

```text
mininet> srv_dhcp tail -n 25 /tmp/dhcp_corp.log
```

Ahora pide DHCP en **un host representativo de cada sede** (mismo comando, cambia el
nombre; con guion bajo la sintaxis corta `nodo comando` de la CLI funciona directa):

```text
mininet> h_a1_v10 dhclient -nw -1 -lf /var/lib/dhcp/dhclient-h_a1_v10.leases -pf /run/dhclient-h_a1_v10.pid h_a1_v10-eth0
mininet> h_a2_v40 dhclient -nw -1 -lf /var/lib/dhcp/dhclient-h_a2_v40.leases -pf /run/dhclient-h_a2_v40.pid h_a2_v40-eth0
mininet> h_b2_v60 dhclient -nw -1 -lf /var/lib/dhcp/dhclient-h_b2_v60.leases -pf /run/dhclient-h_b2_v60.pid h_b2_v60-eth0
```
(Para validar TODOS los hosts de golpe usa el test automático: `sudo python3 test_red.py`.)
Espera ~10 segundos y verifica un par de sedes:

```text
mininet> h_a2_v40 ip -4 addr show h_a2_v40-eth0      # ~ 10.2.40.x
mininet> h_b2_v60 ip -4 addr show h_b2_v60-eth0      # ~ 10.4.60.x
mininet> h_a1_v10 ip -4 addr show h_a1_v10-eth0      # ~ 10.1.10.x
```
**Esperado:** cada host con IP dentro de su subred. (Confirma DHCP centralizado en A1
servido a las 4 sedes a través del WAN mediante `dhcrelay`.)

### 4.4 — Conectividad extremo a extremo entre sedes

```text
mininet> h_a1_v10 ping -c2 10.1.100.4        # host A1 -> servidor web (A1)
mininet> h_a2_v40 ping -c2 10.1.100.5        # host A2 -> servidor FTP (A1, vía WAN)
mininet> h_b1_v50 ping -c2 h_b2_v60          # host B1 -> host B2 (spoke a spoke por el hub)
```
**Esperado:** 0% loss (requiere haber corrido el DHCP del paso 4.3).

### 4.5 — DNS interno (s9)

```text
mininet> h_a2_v40 dig @10.1.100.3 web.corp.local +short      # -> 10.1.100.4
mininet> h_a2_v40 dig @10.1.100.3 ftp.corp.local +short      # -> 10.1.100.5
mininet> h_a2_v40 dig web.corp.local +short                  # sin @: usa el DNS recibido por DHCP
```
**Esperado:** las dos primeras devuelven la IP; la tercera también (el DNS `10.1.100.3`
llegó por opción DHCP). Verifica los registros: `mininet> srv_dns cat /tmp/corp_dns.txt`.

### 4.6 — Servidor Web (s7/s9)

```text
mininet> h_b2_v60 curl -s http://10.1.100.4          # por IP
mininet> h_b2_v60 curl -s http://web.corp.local      # por FQDN (DNS + routing + servicio)
```
**Esperado:** `<h1>Datacenter A1 - Peeda+Vuul (web.corp.local)</h1>`.

### 4.7 — Servidor FTP (s7/s9)

```text
mininet> h_a2_v40 curl -s ftp://admin:secret123@10.1.100.5/           # lista el directorio
mininet> h_a2_v40 curl -s ftp://admin:secret123@ftp.corp.local/       # por FQDN
mininet> h_a2_v40 curl -s ftp://admin:secret123@10.1.100.5/welcome.txt # descarga un archivo
```
**Esperado:** el listado incluye `welcome.txt`; la última descarga muestra
`Archivo de prueba FTP - Peeda+Vuul`. (Funciona en modo pasivo: no hay NAT, así que la
IP que anuncia el FTP es enrutable.)

### 4.8 — `pingall` (opcional, con matiz importante)

```text
mininet> pingall
```
> ⚠️ **`pingall` NO dará 100% y es lo esperado por diseño.** Mininet hace ping a la IP de
> la interfaz primaria de cada nodo: los servidores tienen su IP de servicio en `lo` (no
> en la interfaz primaria), y los enlaces internos `/30` y `172.16.x.x` **no se anuncian
> globalmente** (son infraestructura). La conectividad real se valida con los pasos 4.4–4.7
> (host↔host y host↔servicios), que sí deben ser 100%.

### 4.9 — Redundancia del doble núcleo: FAILOVER (s7)

Simula la caída de **Core-1** bajando TODOS sus enlaces y comprueba que el tráfico sigue por **Core-2**:

```text
mininet> h_a2_v40 ping -c2 10.1.100.4        # OK antes del fallo
mininet> link r_a1 core1 down
mininet> link srv_dhcp core1 down
mininet> link srv_dns core1 down
mininet> link srv_web core1 down
mininet> link srv_ftp core1 down
mininet> h_a2_v40 ping -c4 10.1.100.4        # se recupera por core2
```
Para restaurar: repite los `link ... up`.
> Nota honesta: el ECMP de Linux reparte **por flujo** (hash), no por paquete; por eso la
> redundancia se demuestra con este failover y **no** viendo paquetes alternarse entre cores.
> El routing es estático (sin OSPF/HSRP, no son de clase), así que la recuperación no es
> instantánea: es la limitación que enseña la práctica s7.

---

## 5. Comandos de inspección útiles

```text
mininet> r_a1 ip route                       # tabla de R-A1: ECMP a servidores + rutas WAN a spokes
mininet> core1 ip route                      # default vía R-A1 + /32 a cada servidor
mininet> r_a2 ip route                       # default vía el HUB
mininet> srv_ftp ip addr                     # ve la IP de servicio 10.1.100.5/32 en lo
mininet> r_a2 ip -d link show r_a2-eth0.40   # subinterfaz 802.1Q (VLAN 40)
mininet> sh ovs-vsctl show                   # puertos/VLANs (tag/trunks) de los switches OVS
mininet> sh ovs-appctl fdb/show sw_a2        # tabla MAC (FDB) del switch de A2 (s3)
mininet> srv_dhcp cat /tmp/dhcp_corp.leases  # concesiones DHCP entregadas
mininet> srv_web cat /tmp/web/http.log       # log del servidor web
mininet> srv_ftp cat /tmp/ftp_share/ftp.log  # log del servidor FTP (útil si el FTP no responde)
```
Captura de tráfico (ej. DORA de DHCP en el servidor):
```text
mininet> srv_dhcp tcpdump -n -i any port 67 or port 68
```

---

## 6. Salir y limpiar

```text
mininet> exit
```
```bash
sudo mn -c                                   # limpia la topología
sudo pkill -f dnsmasq ; sudo pkill -f dhcrelay ; sudo pkill -f pyftpdlib   # por si quedan daemons
```

---

## 7. Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| El host no obtiene IP por DHCP | Usa siempre la forma con `-sf/-lf/-pf` del paso 4.3 y mira `srv_dhcp tail -f /tmp/dhcp_corp.log`. Asegúrate de haber hecho las pruebas de routing (4.2) antes; el relay necesita las rutas para el camino de retorno. |
| `dhclient` se queda en bucle DISCOVER/ACK/DECLINE | Se invocó `dhclient` "a pelo" (sin `-lf`/`-pf` privados): al compartir `/var/lib/dhcp` entre hosts, dhclient confunde su estado con un conflicto y rechaza cada IP con DHCPDECLINE. Usa `dhclient_cmd()` de `master_wan.py` o las opciones del paso 4.3. |
| `curl ftp://...` no responde | Verifica que `pyftpdlib` esté instalado (`srv_ftp cat /tmp/ftp_share/ftp.log`; si dice *No module named pyftpdlib*, instala el paquete del paso 2). |
| `dig`/`curl` por FQDN falla pero por IP funciona | Falta el DNS en el host: corre primero el DHCP (4.3); o usa `dig @10.1.100.3 ...` explícito. |
| Errores al arrancar / "interface exists" | Quedó una corrida previa: `sudo mn -c` y vuelve a lanzar. |
| `pingall` con muchas X | Normal (ver 4.8): valida con 4.4–4.7, no con pingall. |
| `dhcrelay: command not found` | Falta `isc-dhcp-relay` (paso 2). |

---

### Mapa rápido de direccionamiento (referencia)

| Recurso | Dirección |
|---|---|
| Supernet / esquema | `10.0.0.0/8`, `10.{sede}.{vlan}.0/24`, gw `.254` |
| WAN /30 | MTY-GDL `10.99.1.0/30` · MTY-QRO `10.99.2.0/30` · MTY-CDMX `10.99.3.0/30` |
| Server farm (A1) | `10.1.100.0/24` → DHCP `.2`, DNS `.3`, Web `.4`, FTP `.5` |
| Infra interna A1 /30 | uplinks `172.16.0.0/30` y `172.16.0.4/30`; trunk cores `172.16.0.8/30`; dual-homing `172.16.1-4.x` |
| Credenciales FTP | usuario `admin` · contraseña `secret123` |
