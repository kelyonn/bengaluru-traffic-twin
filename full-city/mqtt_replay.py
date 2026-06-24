"""
Replay the logged messages to an MQTT broker.

The log (mqtt_logs/mqtt_log.jsonl) is broker-agnostic — every line is a ready
envelope {topic, qos, retain, payload}. This script just publishes them.

Usage:
  pip install paho-mqtt
  python3 mqtt_replay.py --host BROKER_IP [--port 1883] [--realtime] [--speed 30]
                         [--user U --password P] [--type data,alert]

  --realtime   pace messages by their sim_t so the 3-hour peak replays live
  --speed N    sim-seconds per real-second when --realtime (default 30)
  --type       comma list to publish only some message kinds (matches topic suffix)

With no --host it does a DRY RUN: prints what it would publish, contacts nothing.
"""
import json, time, argparse, sys

LOG = "mqtt_logs/mqtt_log.jsonl"

def topic_type(topic):
    return topic.rstrip("/").split("/")[-1]   # data/heartbeat/alert/frames/status

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--speed", type=float, default=30.0)
    ap.add_argument("--type", help="comma list e.g. data,alert")
    args = ap.parse_args()

    want = set(args.type.split(",")) if args.type else None

    client = None
    if args.host:
        import paho.mqtt.client as mqtt
        client = mqtt.Client()
        if args.user:
            client.username_pw_set(args.user, args.password or "")
        client.connect(args.host, args.port, keepalive=60)
        client.loop_start()
        print(f"Connected to {args.host}:{args.port}", flush=True)
    else:
        print("DRY RUN — no --host given, contacting no broker.\n", flush=True)

    sent = 0
    last_sim_t = None
    with open(LOG) as fh:
        for line in fh:
            rec = json.loads(line)
            if want and topic_type(rec["topic"]) not in want:
                continue

            if args.realtime and last_sim_t is not None:
                dt = (rec["sim_t"] - last_sim_t) / args.speed
                if dt > 0:
                    time.sleep(min(dt, 5.0))
            last_sim_t = rec["sim_t"]

            payload = json.dumps(rec["payload"], separators=(",", ":"))
            if client:
                client.publish(rec["topic"], payload, qos=rec["qos"], retain=rec["retain"])
            else:
                if sent < 8:
                    print(f"  [{rec['qos']}{'R' if rec['retain'] else ' '}] "
                          f"{rec['topic']}  {payload[:90]}", flush=True)
            sent += 1
            if sent % 5000 == 0:
                print(f"  …{sent} messages", flush=True)

    if client:
        client.loop_stop(); client.disconnect()
    print(f"\nDone. {'Published' if client else 'Would publish'} {sent} messages.")

if __name__ == "__main__":
    main()
