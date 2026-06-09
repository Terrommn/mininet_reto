# Guía de defensa — Emulación Mininet (Peeda + Vuul)

Esta guía te prepara para **explicar y defender** el proyecto. Está pensada para que la
leas y puedas re-explicar cada parte con tus palabras. Cada técnica está etiquetada con la
**práctica de clase** de la que sale (s2/s3/s7/s8/s9), para que siempre puedas decir
"esto lo vimos en la práctica X".

> **Idea clave para la defensa:** lo que importa no es memorizar, sino entender *por qué*
> cada pieza está ahí. Si entiendes los conceptos de la Sección 1 y los recorridos de la
> Sección 5, puedes responder casi cualquier pregunta.

---

## 0. El proyecto en una frase

> "Emulamos en Mininet la red de la fusión Peeda+Vuul: una topología **hub-and-spoke** con
> Monterrey (A1) como centro, segmentada en **VLANs**, con **inter-VLAN routing**, una **WAN**
> de enlaces dedicados entre sedes, **servicios centralizados** (DHCP, DNS, Web, FTP) y
> **DHCP centralizado con relay** que da direcciones a las 4 sedes."

---

## 1. Conceptos base que debes dominar

| Concepto | Explicación en tus palabras | Práctica |
|---|---|---|
| **VLAN** | Una "red lógica" dentro de un switch. Separa el tráfico aunque los equipos estén en el mismo switch físico (p. ej. Ventas no ve a Dirección). | s3 |
| **Puerto access / puerto trunk** | *Access* = lleva 1 sola VLAN (donde se conecta una PC). *Trunk* = lleva varias VLANs a la vez, etiquetadas. | s3 |
| **802.1Q (tagging)** | El estándar que pone una "etiqueta" de 4 bytes en la trama para marcar a qué VLAN pertenece. Viaja por los trunks. | s3 |
| **Router-on-a-Stick (RoaS)** | Hacer inter-VLAN con UN router que tiene **subinterfaces** (una por VLAN) sobre un solo enlace troncal. Cada subinterfaz es el *gateway* `.254` de su VLAN. | s3 |
| **Inter-VLAN routing** | Para pasar de una VLAN a otra hay que pasar por un router (capa 3). | s3 |
| **Gateway (.254)** | La "puerta de salida" de una subred. Aquí siempre es el `.254`. | s3 |
| **Subred / máscara /24 /30** | `/24` = 254 hosts (lo usamos para las VLANs). `/30` = 2 hosts útiles (lo usamos para enlaces punto-a-punto entre routers). | s2/s7 |
| **Ruta estática / ruta default** | Le dices al router a mano "para llegar a la red X, manda por Y". *Default* = "para todo lo demás, manda por aquí". | s7 |
| **ECMP** | *Equal-Cost Multi-Path*: una ruta con **dos caminos** de igual costo (`nexthop … nexthop …`). Da redundancia. | s7 |
| **Dual-homing** | Un equipo conectado con **dos enlaces** a dos dispositivos distintos, para que si uno falla siga el otro. | s7 |
| **DHCP / DORA** | Protocolo que asigna IPs automáticamente. DORA = Discover, Offer, Request, Ack. | s8 |
| **DHCP relay / giaddr** | Un agente que reenvía el DHCP (que es *broadcast* y no cruza routers) hacia un servidor central, y marca en el campo **giaddr** de qué subred viene. | s8 |
| **DNS** | Traduce nombres (web.corp.local) a IPs (10.1.100.4). | s9 |
| **Loopback (lo)** | Interfaz virtual de un equipo que siempre está "arriba", no atada a un cable físico. | (extensión de s7) |
| **Mininet / OVS / TCLink** | Mininet emula la red; OVS son los switches virtuales; TCLink permite poner ancho de banda/latencia a los enlaces. | s2 |

---

## 2. La arquitectura, y por qué es así

- **Topología hub-and-spoke (estrella):** A1-Monterrey es el HUB; A2, B1, B2 son *spokes* que
  se conectan **solo** al HUB. *¿Por qué?* Es más simple y barato que una malla completa; el
  tráfico entre sucursales pasa por el centro. (Lo justifica el reporte original.)
- **Direccionamiento `10.0.0.0/8` jerárquico:** El problema original era que **las 4 sedes
  usaban la misma `192.168.1.0/24`** y chocaban al unirlas. Se rediseñó con un esquema
  autodocumentado: `10.{sede}.{vlan}.0/24` → mirando la IP sabes la sede y la VLAN.
  - Sede: A1=1, A2=2, B1=3, B2=4. VLAN = tercer octeto. Gateway = `.254`.
  - WAN entre routers: `10.99.{1,2,3}.0/30`.
- **A1 es especial:** además de sus VLANs, tiene el **data center** (servidores) y un **doble
  núcleo** para redundancia. Los spokes son más simples (solo Router-on-a-Stick).

---

## 3. El patrón de diseño: `build()` vs `configure()` (te lo van a preguntar)

Cada sede es una **clase** con dos métodos:

- **`build(net)`** → solo **declara** nodos y enlaces (`addHost`, `addSwitch`, `addLink`).
- **`configure()`** → **configura** (IPs, VLANs, subinterfaces, rutas), y se llama
  **después** de `net.start()`.

**¿Por qué separados?** Porque Mininet **crea las interfaces virtuales recién cuando haces
`net.start()`**. Antes de eso no existen, así que no puedes ponerles IP ni VLAN. Por eso:
primero "dibujas" la red (`build`), arrancas (`net.start()`), y luego la configuras
(`configure`). Es exactamente el orden de las prácticas (en s3/s8/s9 todo lo de `ovs-vsctl`,
`ip link`, `ip addr`, `ip route` se hace **después** de arrancar).

> **Cómo lo dices en la defensa:** "Separamos topología de configuración porque las interfaces
> de Mininet existen hasta que la red arranca; `build` declara, `configure` se ejecuta tras
> `net.start()`."

---

## 4. Archivo por archivo

### 4.1 `common_router.py` — la clase Router (de s7)
Convierte un host normal de Mininet en un **router Linux**:
```python
self.cmd('sysctl -w net.ipv4.ip_forward=1')        # ACTIVA el reenvío: ahora enruta paquetes
self.cmd('sysctl -w net.ipv4.conf.all.rp_filter=0')# permite caminos asimétricos (necesario para ECMP)
self.cmd('modprobe 8021q')                          # habilita subinterfaces VLAN (802.1Q)
```
- `ip_forward=1`: sin esto, un host Linux **descarta** el tráfico que no es para él. Con esto, lo **reenvía** = se comporta como router.
- `rp_filter=0`: el "filtro de ruta inversa" descarta paquetes que entran por una interfaz por la que no saldría la respuesta. Como con ECMP el tráfico puede **entrar por un núcleo y salir por el otro**, hay que apagarlo. (Esto se explica en s7.)
- `modprobe 8021q`: carga el módulo del kernel que permite crear las subinterfaces `eth0.10`, etc.

> Es **casi idéntica** a la clase `Router` de la práctica s7 (le añadimos `modprobe 8021q` de s3).

### 4.2 `site_a2.py` / `site_b1.py` / `site_b2.py` — los spokes (Router-on-a-Stick, s3)
Los tres son iguales; solo cambian el número de sede, el prefijo IP y la lista de VLANs.
Tomemos A2 (Guadalajara):

- **`build()`**: crea el router (`r-a2`, **sin IP** — ver Sección 6), un switch de acceso, un
  host por VLAN, y los enlaces. El último enlace `switch → router` es el **trunk** (`r-a2-eth0`).
- **`configure()`** (tras arrancar):
  1. **Etiqueta los puertos del switch** (s3): cada puerto de PC con su VLAN (`tag=`), y el
     puerto troncal con todas (`trunks=`).
     ```python
     sw.cmd(f'ovs-vsctl set port {self.SWITCH}-eth{i} tag={vid}')   # puerto access
     sw.cmd(f'ovs-vsctl set port {self.TRUNK} trunks={trunk_list}') # puerto trunk
     ```
  2. **Crea las subinterfaces 802.1Q** en el router = los gateways `.254` (s3):
     ```python
     r.cmd(f'ip link add link {self.ROUTER}-eth0 name {sub} type vlan id {vid}')
     r.cmd(f'ip addr add {self.PREFIX}.{vid}.254/24 dev {sub}')
     ```
- **`start_relay()`**: arranca el `dhcrelay` (s8) que manda el DHCP de este spoke al servidor
  central de A1 a través de la WAN.

> Cómo lo dices: "Cada sucursal es un Router-on-a-Stick: un router con una subinterfaz por
> VLAN sobre un trunk; el switch etiqueta los puertos. Es la práctica s3 aplicada a la sede."

### 4.3 `site_a1.py` — el HUB (la parte fuerte)
Combina varias prácticas. Tiene tres "bloques":

**(a) Router de borde R-A1** = Router-on-a-Stick de las VLAN de usuario de A1 + borde de la
WAN hacia los spokes + agente `dhcrelay`. (s3 + s7 + s8)

**(b) Doble núcleo `core1` / `core2`** = dos routers de tránsito con **ECMP** (s7). Dan
redundancia al data center.

**(c) Granja de servidores dual-homed** = `srv-dhcp`, `srv-dns`, `srv-web`, `srv-ftp`. Cada
uno tiene **dos enlaces** (uno a cada núcleo) y su **IP de servicio en loopback** (s7 extendido):
```python
sd.cmd('ip addr add 10.1.100.2/32 dev lo')   # la IP "pública" del servicio va en lo
sd.cmd('ip route replace default '            # y sale por CUALQUIERA de los dos núcleos (ECMP)
       'nexthop via 172.16.1.1 dev srv-dhcp-eth0 '
       'nexthop via 172.16.1.5 dev srv-dhcp-eth1')
```
Rutas clave del HUB:
```python
# R-A1 llega a los servidores por los DOS núcleos (ECMP):
r.cmd('ip route replace 10.1.100.0/24 nexthop via 172.16.0.2 dev r-a1-eth1 '
      'nexthop via 172.16.0.6 dev r-a1-eth2')
# cada núcleo: todo lo demás se manda a R-A1, y cada servidor por su /30 directo:
c1.cmd('ip route replace default via 172.16.0.1 dev core1-eth0')
c1.cmd('ip route replace 10.1.100.2/32 via 172.16.1.2 dev core1-eth2')
```
**Servicios** (`start_services`): DNS y DHCP con `dnsmasq` (s8/s9), Web con `http.server`
(s7/s9), FTP con `pyftpdlib` (s7/s9).

### 4.4 `master_wan.py` — el integrador (patrón modular de s7)
Es el único que se ejecuta (`sudo python3 master_wan.py`). Hace, **en orden**:
1. Crea **una sola** red Mininet.
2. `build()` de las 4 sedes + cablea la **WAN** (3 enlaces `/30` desde R-A1 a cada spoke, con
   ancho de banda 10/10/20 Mbps usando TCLink, s2).
3. `net.start()`.
4. Pone las IPs de la WAN, llama a `configure()` de cada sede, y fija las **rutas WAN**:
   ```python
   r.cmd('ip route replace 10.2.0.0/16 via 10.99.1.2 dev r-a1-eth3')   # R-A1 -> GDL
   a2.gateway.cmd('ip route replace default via 10.99.1.1 dev r-a2-eth1') # GDL -> todo via HUB
   ```
5. Genera las configs (`/tmp/dhcp_corp.conf`, zona DNS), arranca servicios y `dhcrelay`.
6. Abre la CLI.

> Es **literalmente** el patrón de s7 (`site_a.py`, `site_b.py`, `master_wan.py`), escalado a 4 sedes.

---

## 5. Recorridos de paquetes (lo que MÁS preguntan)

### 5.1 Inter-VLAN local (PC de Dirección → PC de TI, en A1)
1. La PC de VLAN 10 manda a su gateway `10.1.10.254` (subinterfaz `r-a1-eth0.10`).
2. R-A1 ve que el destino está en `10.1.20.0/24`, que tiene conectada en `r-a1-eth0.20`.
3. Reenvía la trama **etiquetada como VLAN 20** por el trunk → switch → PC de TI.
> Sin el router, las dos VLANs **no** se verían (están aisladas). El router es el único punto
> de paso entre VLANs. (s3)

### 5.2 ⭐ Un host pide IP por DHCP (con relay a través de la WAN) — el flujo estrella
Ejemplo: `h-b1-v50` (Querétaro, VLAN 50) pide IP al servidor central de A1.
1. El host manda un **DISCOVER** (broadcast) → llega a `r-b1-eth0.50` (su gateway en R-B1).
2. El **`dhcrelay`** de R-B1 lo atrapa, escribe `giaddr = 10.3.50.254` y lo manda **unicast**
   al servidor `10.1.100.2`.
3. R-B1 enruta hacia `10.1.100.2` por su **default → R-A1** (cruza la WAN).
4. R-A1 lo manda al servidor por **ECMP** (núcleo1 o núcleo2) → el núcleo tiene una ruta `/32`
   al servidor → llega a `srv-dhcp`.
5. `dnsmasq` mira el `giaddr` (10.3.50.254), elige el **pool de esa subred**
   (`10.3.50.50–150`) y manda el **OFFER** de vuelta al `giaddr`.
6. El OFFER regresa: servidor → núcleo (ECMP) → R-A1 → WAN → R-B1.
7. El `dhcrelay` de R-B1 (que también escucha en la interfaz WAN) lo recibe y se lo entrega al
   host. Request/Ack repiten el camino. El host queda con IP, gateway `.254` y DNS `10.1.100.3`.

> Cómo lo dices: "El DHCP es broadcast y no cruza routers, así que cada sede corre un
> **relay** que lo convierte en unicast al servidor central; el servidor sabe de qué subred
> viene por el campo **giaddr** y entrega del pool correcto." (s8)

### 5.3 Un host navega a `web.corp.local`
1. El host pregunta al DNS `10.1.100.3` (que recibió por DHCP) → responde `10.1.100.4` (s9).
2. El host abre HTTP a `10.1.100.4` → su gateway → R-A1 → ECMP a un núcleo → servidor web.
3. `python3 -m http.server` responde el HTML. (s7/s9)

### 5.4 Cómo se alcanza un servidor dual-homed
- **Ida:** host → R-A1 → R-A1 reparte `10.1.100.0/24` por **ECMP** entre los dos núcleos →
  el núcleo tiene `/32` al servidor por su `/30` directo → llega a la IP en `lo`.
- **Vuelta:** servidor → **default ECMP** por cualquiera de sus dos núcleos → el núcleo manda
  a R-A1 (su default) → R-A1 al host. Como puede **entrar por un núcleo y salir por el otro**,
  hace falta `rp_filter=0`.

### 5.5 Spoke ↔ spoke (Guadalajara → Querétaro)
Sale por el **default** del router de GDL hacia el HUB → R-A1 mira su tabla, ve `10.3.0.0/16
via WAN` → lo manda a QRO. **El hub hace de tránsito** (por eso necesita `ip_forward`).

---

## 6. Las decisiones "avanzadas", explicadas para defenderlas

### 6.1 Doble núcleo con ECMP (en vez de HSRP)
- **Qué hace:** dos routers de núcleo dan dos caminos; con ECMP (`nexthop … nexthop …`) el
  tráfico usa los dos. Si uno cae, queda el otro (**redundancia**).
- **Por qué ECMP y no HSRP:** HSRP/VRRP (una IP virtual compartida entre los dos núcleos)
  **solo se mencionó** en clase (s8), no se implementó. ECMP **sí** se implementó (s7). Por la
  restricción de "solo lo de clase", usamos ECMP.
- **Honestidad (dilo tú primero):** el ECMP de Linux reparte **por flujo** (hash), no por
  paquete; por eso la redundancia se demuestra con **failover** (bajar los enlaces de un
  núcleo), no viendo paquetes alternarse.

### 6.2 IP de servicio en loopback + rutas /32
- **Por qué:** un servidor dual-homed tiene **dos** IPs físicas (una por enlace `/30`). Si la
  IP del servicio estuviera en una de ellas, dependería de ese cable/núcleo. Poniéndola en
  **`lo`** (que nunca se cae) es alcanzable por **cualquiera** de los dos núcleos — que es
  justo el punto del dual-homing. Los núcleos anuncian una ruta `/32` hacia esa IP.

### 6.3 `ip=None` en routers y servidores (el detalle fino que más impresiona)
- **El problema:** si no pones `ip=None`, Mininet le asigna por defecto `10.0.0.x/8` a la
  primera interfaz. Una ruta conectada **/8** abarcaría **todo** `10.0.0.0/8` y
  **secuestraría** el enrutamiento de toda la red.
- **La solución:** `ip=None` → nosotros asignamos las IPs reales nosotros mismos.
> Si te preguntan por esto, es señal de que entendiste Mininet a fondo. Buen punto a tu favor.

### 6.4 `dhcrelay` escuchando también en la interfaz WAN (upstream)
El relay debe escuchar en las subinterfaces de VLAN (donde llega el DISCOVER) **y** en la
interfaz por donde **vuelve** el OFFER del servidor (la WAN). Por eso la incluimos en `-i`.

---

## 7. Limitaciones honestas (menciónalas tú antes de que te las pregunten)

| Limitación | Por qué / cómo se defiende |
|---|---|
| El failover del doble núcleo no es instantáneo | Routing **estático**: no reconverge solo. Es **la lección de la práctica s7**; un protocolo dinámico (OSPF) lo resolvería, pero no es de clase. |
| ECMP por flujo (no se ve balanceo paquete a paquete) | Comportamiento normal del kernel; se demuestra redundancia con `link … down`. |
| Usamos `/24` y no `/28` como el reporte | En `/28` el gateway `.254` **no existe**; `/24` simplifica y deja válido el `.254`. Es una simplificación de emulación documentada. |
| El WiFi no se emula como tal | Mininet base no tiene radio; las VLANs WiFi (130/140) se representan como un host cableado en esa VLAN. |
| No hay Internet/NAT real | No era necesario para DHCP/DNS/Web/FTP; los spokes apuntan su default al hub. |
| `pingall` no da 100% | Las IP de servicio están en `lo` y los `/30` internos no se anuncian globalmente (por diseño). Se valida con pruebas dirigidas. |

---

## 8. Mapa maestro: técnica → práctica de clase

| Técnica en el proyecto | Archivo | Práctica |
|---|---|---|
| Mininet, `OVSSwitch`, `TCLink`, ancho de banda/latencia | todos / WAN | **s2** |
| VLANs, trunk/access (`ovs-vsctl tag/trunks`), Router-on-a-Stick (subinterfaces 802.1Q), gateways `.254` | spokes + A1 | **s3** |
| Clase `Router`, `ip_forward`, `rp_filter`, **ECMP** (`nexthop … nexthop`), **dual-homing**, diseño **modular** (site + master), rutas estáticas, Web/FTP | A1 + master | **s7** |
| **DHCP** central con `dnsmasq` + **`dhcrelay`** + `giaddr` | A1 + spokes | **s8** |
| **DNS** con `dnsmasq` (zona interna, FQDNs `*.corp.local`), 3-tier/server farm | A1 | **s9** |

> Frase para la defensa: "No usamos nada fuera de clase: s2 (Mininet/enlaces), s3 (VLANs/RoaS),
> s7 (router/ECMP/modular/servicios), s8 (DHCP relay) y s9 (DNS)."

---

## 9. Banco de preguntas de defensa (con respuestas)

**P: ¿Por qué hub-and-spoke y no una malla?**
R: Más simple y económico; el tráfico entre sucursales pasa por el hub central (Monterrey),
que además tiene los servidores. Lo justifica el reporte.

**P: ¿Por qué rediseñaron el direccionamiento a `10.0.0.0/8`?**
R: Las 4 sedes usaban la misma `192.168.1.0/24` y chocaban al fusionarlas. Con
`10.{sede}.{vlan}.0/24` no hay choques y la IP "se autodocumenta".

**P: ¿Qué es Router-on-a-Stick y dónde está?**
R: Hacer inter-VLAN con un router que tiene una subinterfaz 802.1Q por VLAN sobre un solo
trunk. Está en los 3 spokes (y también en A1 para sus VLANs de usuario). Es la práctica s3.

**P: ¿Cómo se comunican dos VLANs distintas?**
R: A través del router (capa 3); el switch solo conmuta dentro de la misma VLAN.

**P: ¿Por qué el DHCP necesita un relay?**
R: El DISCOVER es broadcast y no cruza routers. El relay lo reenvía como unicast al servidor
central y marca en `giaddr` la subred de origen, para que el servidor entregue del pool correcto.

**P: Si el servidor está en A1, ¿cómo recibe IP un host de CDMX?**
R: El router de CDMX corre `dhcrelay` que manda el DHCP por la WAN a `10.1.100.2`; la respuesta
vuelve por la WAN y el relay se la entrega al host. (Ver Sección 5.2.)

**P: ¿Por qué dos núcleos?**
R: Redundancia del data center. Si un núcleo falla, los servidores siguen accesibles por el otro.

**P: ¿Por qué ECMP y no HSRP?**
R: HSRP solo se mencionó en clase; no se implementó. ECMP sí (s7). Cumplimos "solo lo de clase".

**P: ¿El ECMP balancea carga?**
R: Reparte **por flujo** (hash de origen/destino), no por paquete. Sirve para redundancia y
para repartir flujos distintos entre los dos caminos.

**P: ¿Por qué la IP del servidor está en `lo` (loopback)?**
R: Para que sea alcanzable por **cualquiera** de los dos núcleos (dual-homing). Si estuviera en
una NIC física, dependería de ese enlace.

**P: ¿Qué pasa si cae el núcleo 1?**
R: El tráfico continúa por el núcleo 2 (failover). Se demuestra con `link r-a1 core1 down`.
No es instantáneo porque el routing es estático (limitación que enseña s7).

**P: ¿Por qué `/24` y no `/28` como el reporte?**
R: Para que el gateway `.254` sea válido (en `/28` no cabe) y simplificar la emulación. Está documentado.

**P: ¿Por qué un archivo por sede + un maestro?**
R: Modularidad (patrón de s7): cada sede es una clase reutilizable y el maestro las integra en
una sola red Mininet.

**P: ¿Por qué `controller=None` y `failMode='standalone'`?**
R: No usamos SDN/OpenFlow; los switches actúan como switches normales y las VLANs se configuran
con `ovs-vsctl`. Es como en s3/s8/s9.

**P: ¿Para qué sirve `TCLink`?**
R: Permite poner ancho de banda y latencia a los enlaces (s2). Lo usamos en la WAN (10/10/20 Mbps).

**P: ¿Por qué los hosts no tienen IP fija?**
R: Para demostrar el DHCP. La obtienen por DHCP relay.

**P: ¿`dnsmasq`, `pyftpdlib`, `http.server` son de clase?**
R: Sí: DHCP/DNS con `dnsmasq` (s8/s9), Web con `http.server` (s7/s9), FTP con `pyftpdlib` (s7/s9).

**P: ¿Qué hace `rp_filter=0`?**
R: Apaga el filtro de ruta inversa para permitir caminos asimétricos (entrar por un núcleo,
salir por otro), necesario con ECMP. (s7)

**P: ¿Y si `pingall` no da 100%?**
R: Es esperado: las IP de servicio están en `lo` y los `/30` internos no se anuncian
globalmente. La conectividad real se valida con pruebas dirigidas (ver README).

---

## 10. Glosario rápido de comandos (por si te señalan una línea)

| Comando | Qué hace |
|---|---|
| `sysctl -w net.ipv4.ip_forward=1` | Hace que el equipo **enrute** (se comporte como router). |
| `sysctl -w net.ipv4.conf.all.rp_filter=0` | Permite caminos asimétricos (para ECMP). |
| `modprobe 8021q` | Carga el soporte de VLANs 802.1Q en el kernel. |
| `ip link add link eth0 name eth0.10 type vlan id 10` | Crea la **subinterfaz** de la VLAN 10. |
| `ip addr add 10.1.10.254/24 dev eth0.10` | Le pone la IP de **gateway** a esa subinterfaz. |
| `ovs-vsctl set port X tag=10` | Marca un puerto del switch como **access** de la VLAN 10. |
| `ovs-vsctl set port X trunks=10,20,...` | Marca un puerto como **trunk** (varias VLANs). |
| `ip route replace 10.1.100.0/24 nexthop via A nexthop via B` | Ruta con **ECMP** (dos caminos). |
| `ip route replace default via X` | Ruta **por defecto** (para todo lo no específico). |
| `ip addr add 10.1.100.2/32 dev lo` | IP de **servicio** en el loopback. |
| `dhcrelay -4 -i <ifs> 10.1.100.2` | Agente **relay** de DHCP hacia el servidor central. |
| `dnsmasq --conf-file=...` | Servidor **DHCP** (y/o DNS). |
| `python3 -m http.server 80` | Servidor **web** simple. |
| `python3 -m pyftpdlib -i 0.0.0.0 -p 21 -w -u admin -P secret123` | Servidor **FTP**. |

---

### Cierre
Si dominas la **Sección 1** (conceptos), la **Sección 5** (recorridos) y la **Sección 6**
(decisiones avanzadas), puedes defender el proyecto completo. Todo se apoya en s2/s3/s7/s8/s9
— no hay nada fuera de lo visto en clase, solo **integrado** a mayor escala.
