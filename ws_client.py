import asyncio
import websockets
import pyaudio

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

class AudioClient:
    def __init__(self):
        self.pya = pyaudio.PyAudio()
        self.audio_in_queue = asyncio.Queue()
        self.out_queue = asyncio.Queue(maxsize=5)
        
    async def send_realtime(self, websocket):
        while True:
            msg = await self.out_queue.get()
            await websocket.send(msg['data'])

    async def handle_audio_input(self):
        stream_in = self.pya.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE
        )
        
        while True:
            data = stream_in.read(CHUNK_SIZE, exception_on_overflow=False)
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})

    async def receive_audio(self, websocket):
        print("Starting receive_audio handler")
        while True:
            try:
                data = await websocket.recv()
                if isinstance(data, bytes):
                    # Put directly into the queue for play_audio to handle
                    await self.audio_in_queue.put(data)
                    print(f"Queued audio data: {len(data)} bytes")
                elif isinstance(data, str):
                    print(f"Received text: {data}")
            except websockets.ConnectionClosed:
                print("WebSocket connection closed")
                return  # Exit cleanly instead of breaking


    async def play_audio(self):
        stream_out = self.pya.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE
        )
        
        while True:
            data = await self.audio_in_queue.get()
            stream_out.write(data)

    async def run(self):
        uri = "ws://localhost:8000/ws"
        async with websockets.connect(uri) as websocket:
            tasks = [
                asyncio.create_task(self.send_realtime(websocket)),
                asyncio.create_task(self.handle_audio_input()),
                asyncio.create_task(self.receive_audio(websocket)),
                asyncio.create_task(self.play_audio())
            ]
            
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                print(f"Error in tasks: {e}")
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self.pya.terminate()

if __name__ == "__main__":
    client = AudioClient()
    asyncio.run(client.run())
