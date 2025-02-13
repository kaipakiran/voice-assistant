from fastapi import FastAPI, WebSocket
import asyncio
import base64
import io
import cv2
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import pyaudio
import PIL.Image
import mss
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch

from pygame import mixer, time
from io import BytesIO


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024
MODEL = "models/gemini-2.0-flash-exp"

# pya = pyaudio.PyAudio()
class WebSocketAudioLoop:
    def __init__(self, websocket: WebSocket, video_mode: str = "none"):
        self.websocket = websocket
        self.video_mode = video_mode
        self.audio_in_queue = asyncio.Queue()
        self.out_queue = asyncio.Queue(maxsize=5)
        self.client = genai.Client(http_options={"api_version": "v1alpha"})
        self.pya = pyaudio.PyAudio()
        google_search_tool = Tool(
                                google_search = GoogleSearch()
                            )
        self.config = {
            "generation_config": {"response_modalities": ["AUDIO"]},
            "tools": [google_search_tool],
            "systemInstruction": "You are a polite and friendly assistant. Please respond in a freindly and courteus voice"}

        # self.config['generation_config']['tools']= [{"google_search": {}}]
        # self.config = GenerateContentConfig(
        #     response_modalities=["AUDIO"],
        #     tools=[google_search_tool]
        # )
        
    async def send_realtime(self, session):
        while True:
            msg = await self.out_queue.get()
            # print(f"Sending message: {msg}")
            await session.send(msg)
            
    # async def _stream_camera(self, session):
    #     cap = await asyncio.to_thread(cv2.VideoCapture, 0)
    #     while True:
    #         ret, frame = await asyncio.to_thread(cap.read)
    #         if not ret:
    #             break
    #         frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    #         img = PIL.Image.fromarray(frame_rgb)
    #         img.thumbnail([1024, 1024])
            
    #         image_io = io.BytesIO()
    #         img.save(image_io, format="jpeg")
    #         image_io.seek(0)
            
    #         await self.out_queue.put({
    #             "mime_type": "image/jpeg",
    #             "data": base64.b64encode(image_io.read()).decode()
    #         })
    #         await asyncio.sleep(1.0)
    #     cap.release()

    # async def _stream_screen(self, session):
    #     while True:
    #         sct = mss.mss()
    #         monitor = sct.monitors[0]
    #         screenshot = sct.grab(monitor)
            
    #         image_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
    #         img = PIL.Image.open(io.BytesIO(image_bytes))
            
    #         image_io = io.BytesIO()
    #         img.save(image_io, format="jpeg")
    #         image_io.seek(0)
            
    #         await self.out_queue.put({
    #             "mime_type": "image/jpeg",
    #             "data": base64.b64encode(image_io.read()).decode()
    #         })
    #         await asyncio.sleep(1.0)

    async def handle_audio_input(self):
        while True:
            try:
                # Receive audio data from WebSocket
                data = await self.websocket.receive_bytes()
                print(f"Received audio data: {len(data)} bytes")
                await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
            except Exception as e:
                break

    async def play_audio(self):
        stream = await asyncio.to_thread(
            self.pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            # bytestream = BytesIO(bytestream)
            # mixer.init()
            # mixer.Sound(bytestream).play()
            await self.websocket.send_bytes(bytestream)

    async def receive_audio(self, session):
        print("Starting receive_audio handler")
        while True:
            try:
                print("Receiving audio response")
                turn = session.receive()
                async for response in turn:
                    
                    if data := response.data:
                        print("Sending audio response towards client")
                        print(f"Data length: {len(data)} bytes")
                        # print(f"Data: {data}")
                        await self.audio_in_queue.put(data)
                        print("Audio response sent")
                        # mixer.init()
                        # mixer.Sound(data).play()
                        # while mixer.music.get_busy():
                        #     time.Clock().tick(10)
                        # # Send audio response back through WebSocket
                        # await self.websocket.send_bytes(data)
                    if text := response.text:
                        await self.websocket.send_text(text)
            except Exception as e:
                print(f"Error in handle_audio_input: {e}")
                break

    

    async def run(self):
        async with self.client.aio.live.connect(model=MODEL, config=self.config) as session:
            tasks = [
                asyncio.create_task(self.send_realtime(session)),
                asyncio.create_task(self.handle_audio_input()),
                asyncio.create_task(self.receive_audio(session)),
                asyncio.create_task(self.play_audio())
            ]
            
            # if self.video_mode == "camera":
            #     tasks.append(asyncio.create_task(self._stream_camera(session)))
            # elif self.video_mode == "screen":
            #     tasks.append(asyncio.create_task(self._stream_screen(session)))
            
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                for task in tasks:
                    task.cancel()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        # video_mode = await websocket.receive_text()
        audio_loop = WebSocketAudioLoop(websocket, video_mode="none")
        await audio_loop.run()
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()




@app.get("/")
async def read_root():
    return FileResponse("static/index.html")


