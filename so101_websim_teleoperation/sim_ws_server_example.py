#!/usr/bin/env python
import asyncio, json, time, traceback
import websockets

JOINT_NAMES = ["shoulder_pan","shoulder_lift","elbow_flex","wrist_flex","wrist_roll","gripper"]
q = [0.0]*len(JOINT_NAMES)

async def rx_loop(ws):
    """Receive commands continuously; update q and log."""
    global q
    async for msg in ws:
        try:
            d = json.loads(msg)
        except Exception:
            print("[sim] bad json")
            continue

        t = d.get("type")
        if t != "cmd":
            # you should only see "state" here if you later add other messages
            print("[sim] non-cmd message:", t)
            continue

        if d.get("mode") != "joint_position":
            print("[sim] unsupported mode:", d.get("mode"))
            continue

        tgt = d.get("target", [])
        if not (isinstance(tgt, list) and len(tgt) == len(JOINT_NAMES)):
            print("[sim] bad target len:", len(tgt))
            continue

        q[:] = tgt
        # log first few joints so we don’t spam
        print("[sim <-cmd]", ", ".join(f"{v:+.3f}" for v in q[:6]), "…")

async def tx_loop(ws):
    """Send state at ~60 Hz."""
    while True:
        state = {
            "type": "state",
            "names": JOINT_NAMES,
            "joint_pos": q,
            "timestamp": time.time()
        }
        try:
            await ws.send(json.dumps(state))
        except websockets.ConnectionClosed:
            break
        await asyncio.sleep(1/60)

async def handle(ws):
    peer = ws.remote_address
    print(f"[sim] client connected: {peer}")
    try:
        await asyncio.gather(rx_loop(ws), tx_loop(ws))
    except websockets.ConnectionClosed:
        print("[sim] client disconnected")
    except Exception:
        print("[sim] handler exception:\n" + traceback.format_exc())

async def main():
    host, port = "127.0.0.1", 8765
    async with websockets.serve(
        handle, host, port,
        ping_interval=None,   # no keepalive pings
        max_queue=2
    ):
        print(f"[sim] WebSocket server running on ws://{host}:{port}")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
