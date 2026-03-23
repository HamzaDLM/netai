from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, asdict
from confluent_kafka import Producer
from typing import Any


@dataclass(slots=True)
class SyslogMessage:
    syslog_timestamp: int
    syslog_hostname: str
    syslog_message: str


ROUTER_HOSTS = ["router-edge-1", "router-edge-2", "router-core-1"]
SWITCH_HOSTS = ["sw-access-1", "sw-access-2", "sw-dist-1", "sw-core-1"]
FIREWALL_HOSTS = ["fw-perimeter-1", "fw-dc-1"]
VPN_HOSTS = ["vpn-gw-1", "vpn-gw-2"]
WLC_HOSTS = ["wlc-1"]

INTERFACES = [
    "GigabitEthernet0/1",
    "GigabitEthernet0/2",
    "GigabitEthernet1/0/24",
    "TenGigabitEthernet1/1",
    "Port-channel10",
    "Vlan10",
]


def random_ip() -> str:
    return (
        f"{random.randint(10, 223)}."
        f"{random.randint(0, 255)}."
        f"{random.randint(0, 255)}."
        f"{random.randint(1, 254)}"
    )


def generate_log() -> SyslogMessage:
    event_generators = [
        lambda: (
            random.choice(SWITCH_HOSTS),
            f"Interface {random.choice(INTERFACES)} changed state to {random.choice(['up', 'down'])}",
        ),
        lambda: (
            random.choice(ROUTER_HOSTS),
            f"%OSPF-5-ADJCHG: Process 1, Nbr {random_ip()} on {random.choice(INTERFACES)} from FULL to DOWN, Neighbor Down: Dead timer expired",
        ),
        lambda: (
            random.choice(ROUTER_HOSTS),
            f"%BGP-5-ADJCHANGE: neighbor {random_ip()} {random.choice(['Up', 'Down'])} {random.choice(['BGP Notification sent', 'Hold Timer Expired', 'Admin shutdown'])}",
        ),
        lambda: (
            random.choice(SWITCH_HOSTS),
            f"%STP-2-LOOPGUARD_BLOCK: Loop guard blocking port {random.choice(INTERFACES)} on VLAN{random.choice([10, 20, 30, 100])}",
        ),
        lambda: (
            random.choice(SWITCH_HOSTS),
            f"%CDP-4-NATIVE_VLAN_MISMATCH: Native VLAN mismatch discovered on {random.choice(INTERFACES)} (10), with {random.choice(SWITCH_HOSTS)} {random.choice(INTERFACES)} (20)",
        ),
        lambda: (
            random.choice(FIREWALL_HOSTS),
            f"%ASA-4-106023: Deny tcp src outside:{random_ip()}/{random.randint(1024, 65535)} dst inside:{random_ip()}/{random.choice([22, 80, 443, 3389])} by access-group OUTSIDE-IN",
        ),
        lambda: (
            random.choice(FIREWALL_HOSTS),
            f"%ASA-6-302013: Built outbound TCP connection {random.randint(100000, 999999)} for outside:{random_ip()}/{random.randint(1024, 65535)} to inside:{random_ip()}/{random.choice([53, 80, 443])}",
        ),
        lambda: (
            random.choice(VPN_HOSTS),
            f"%CRYPTO-5-IKE_SA_UP: IKEv2 SA established for peer {random_ip()} using proposal AES256-SHA256-DH14",
        ),
        lambda: (
            random.choice(VPN_HOSTS),
            f"%CRYPTO-4-IKE_SA_DOWN: IKEv2 SA deleted for peer {random_ip()} reason={random.choice(['DPD timeout', 'Peer closed connection', 'Auth failed'])}",
        ),
        lambda: (
            random.choice(ROUTER_HOSTS),
            f"%SEC_LOGIN-5-LOGIN_SUCCESS: Login Success [user: {random.choice(['admin', 'netops', 'noc'])}] [Source: {random_ip()}] [localport: 22]",
        ),
        lambda: (
            random.choice(ROUTER_HOSTS),
            f"%SEC_LOGIN-4-LOGIN_FAILED: Login failed [user: {random.choice(['admin', 'guest', 'root'])}] [Source: {random_ip()}] [localport: 22] [{random.choice(['Authentication failed', 'Invalid username'])}]",
        ),
        lambda: (
            random.choice(SWITCH_HOSTS),
            f"%LINK-3-UPDOWN: Interface {random.choice(INTERFACES)}, changed state to down due to {random.choice(['loss of signal', 'remote fault', 'err-disable'])}",
        ),
        lambda: (
            random.choice(SWITCH_HOSTS),
            f"%ETHPORT-5-IF_UP: Interface {random.choice(INTERFACES)} is up in mode trunk",
        ),
        lambda: (
            random.choice(ROUTER_HOSTS),
            f"%LINEPROTO-5-UPDOWN: Line protocol on Interface {random.choice(INTERFACES)}, changed state to {random.choice(['up', 'down'])}",
        ),
        lambda: (
            random.choice(FIREWALL_HOSTS),
            "%ASA-1-105008: (Primary) Testing if this device is active for failover group 1",
        ),
        lambda: (
            random.choice(FIREWALL_HOSTS),
            f"%ASA-2-210007: LU allocate translation creation failed for icmp src inside:{random_ip()} dst outside:{random_ip()}",
        ),
        lambda: (
            random.choice(WLC_HOSTS),
            f"%WLAN-6-CLIENT_ASSOCIATED: Station {':'.join(f'{random.randint(0,255):02x}' for _ in range(6))} associated to AP AP-{random.randint(1, 40)} on WLAN {random.choice(['CorpWiFi', 'GuestWiFi'])}",
        ),
        lambda: (
            random.choice(WLC_HOSTS),
            f"%WLAN-4-CLIENT_DISASSOCIATED: Station {':'.join(f'{random.randint(0,255):02x}' for _ in range(6))} disassociated from AP AP-{random.randint(1, 40)} reason={random.choice(['Inactivity timeout', 'AP busy', 'Client request'])}",
        ),
        lambda: (
            random.choice(SWITCH_HOSTS),
            f"%POE-3-CONTROLLER_PORT_ERR: Interface {random.choice(INTERFACES)} power denied due to {random.choice(['over-current', 'power budget exceeded'])}",
        ),
        lambda: (
            random.choice(ROUTER_HOSTS),
            f"%SYS-5-CONFIG_I: Configured from console by {random.choice(['admin', 'netops'])} on vty0 ({random_ip()})",
        ),
    ]

    hostname, message = random.choice(event_generators)()
    return SyslogMessage(
        syslog_timestamp=int(time.time()),
        syslog_hostname=hostname,
        syslog_message=message,
    )


async def produce_batch(
    producer: Producer, topic: str, messages: list[dict[str, Any]]
) -> None:
    loop = asyncio.get_event_loop()
    futures: list[asyncio.Future] = []

    def delivery_callback(fut: asyncio.Future, err, msg):
        if err:
            fut.set_exception(err)
        else:
            fut.set_result(msg)

    for message in messages:
        fut = loop.create_future()
        producer.produce(
            topic,
            json.dumps(message).encode(),
            callback=lambda err, msg, fut=fut: delivery_callback(fut, err, msg),
        )
        futures.append(fut)

    producer.flush()  # ensure all messages are pushed to Kafka
    if futures:
        await asyncio.gather(*futures)


async def main() -> None:
    producer = Producer({"bootstrap.servers": "localhost:9092"})
    batch_size = 100_000
    interval = 0.5  # seconds

    while True:
        batch = [asdict(generate_log()) for _ in range(batch_size)]
        await produce_batch(producer, "syslogs", batch)
        print(f"Sent batch of {batch_size} messages")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
