# Emulacion Mininet - Red Peeda+Vuul (TC2006B)
# Imagen autocontenida: trae mininet, OVS y todos los servicios (dnsmasq,
# dhcrelay, pyftpdlib...). Solo requiere Docker en la maquina anfitriona.
#
#   construir:  docker compose build        (o: docker build -t mininet-reto .)
#   test:       docker compose run --rm red test
#   CLI:        docker compose run --rm red
#
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        mininet \
        openvswitch-switch \
        dnsmasq \
        isc-dhcp-relay \
        isc-dhcp-client \
        dnsutils \
        curl \
        iputils-ping \
        iproute2 \
        net-tools \
        tcpdump \
        procps \
        psmisc \
        kmod \
        python3 \
        python3-pyftpdlib \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY common_router.py site_a1.py site_a2.py site_b1.py site_b2.py \
     master_wan.py test_red.py README.md GUIA_DEFENSA.md entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
# sin argumentos abre la CLI de mininet; "test" corre test_red.py
CMD ["cli"]
