"""
Bark TTS extension for https://github.com/oobabooga/text-generation-webui/
All credit for the amazing tts model goes to https://github.com/suno-ai/bark 
"""
import hashlib
from http.client import IncompleteRead
import os
import time
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

# Read .env file
load_dotenv()

# Should change this environment variable before import bark
model_path = Path(os.environ.get('MODEL_PATH', 'extensions/bark_tts/models/'))
os.environ['XDG_CACHE_HOME'] = model_path.resolve().as_posix()

import nltk
import gradio as gr
import numpy as np
from bark import SAMPLE_RATE, preload_models
from bark.generation import ALLOWED_PROMPTS, generate_text_semantic
from bark.api import semantic_to_waveform
from modules import shared
from scipy.io.wavfile import write as write_wav

nltk.download('punkt')

params =  {
    'activate': True,
    'autoplay': False,
    'forced_speaker_enabled': False,
    'forced_speaker': 'Man',
    'show_text': False,
    'modifiers': [],
    'use_small_models': os.environ.get("USE_SMALL_MODELS", 'false').lower() == 'true',
    'use_cpu': os.environ.get("USE_CPU", 'false').lower() == 'true',
    'force_manual_download': False,
    'voice': 'v2/en_speaker_3',
    'sample_rate': SAMPLE_RATE,
    'temperature': 0.7
}

input_hijack = {
    'state': False,
    'value': ["", ""]
}

streaming_state = shared.args.no_stream
forced_modes = ["Man", "Woman", "Narrator"]
modifier_options = ["[laughter]","[laughs]","[sighs]","[music]","[gasps]","[clears throat]"]
voice_presets = sorted(list(ALLOWED_PROMPTS))

def manual_model_preload():
    for model in ["text","coarse","fine","text_2","coarse_2","fine_2"]:
        remote_url=f"https://dl.suno-models.io/bark/models/v0/{model}.pt"
        remote_md5=hashlib.md5(remote_url.encode()).hexdigest()
        out_path = f"{os.path.expanduser('~/.cache/suno/bark_v0')}/{remote_md5}.pt"
        if not Path(out_path).exists():
            print(f"\t+ Downloading {model} model to {out_path}...")
            # we also have to do some user agent tomfoolery to get the download to work
            req = urllib.request.Request(remote_url, headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/112.0'})
            with urllib.request.urlopen(req) as response, open(out_path, 'wb') as out_file:
                try:
                    data = response.read()
                except IncompleteRead as e:
                    data = e.partial
                out_file.write(data)
        else:
            print(f"\t+ {model} model already exists, skipping...")
    preload_models(
        text_use_gpu= not params['use_cpu'],
        text_use_small= params['use_small_models'],
        coarse_use_gpu= not params['use_cpu'],
        coarse_use_small=params['use_small_models'],
        fine_use_gpu= not params['use_cpu'],
        fine_use_small=params['use_small_models'],
        codec_use_gpu= not params['use_cpu']
    )

def input_modifier(string):
    if not params['activate']:
        shared.processing_message = "*Is typing...*"
        return string
    shared.processing_message = "*Is recording a voice message...*"
    shared.args.no_stream = True
    return string
    
def output_modifier(string):
        
    if not params['activate']:
        return string
    
    ttstext = string
    
    if params['modifiers']:
        ttstext = f"{' '.join(params['modifiers'])}: {ttstext}"
    
    if params['forced_speaker_enabled']:
        ttstext = f"{params['forced_speaker'].upper()}: {ttstext}"
    
    sentences = nltk.sent_tokenize(ttstext)
    silence = np.zeros(int(0.25 * params['sample_rate']))  # quarter second of silence
    pieces = []
    for sentence in sentences:
        semantic_tokens = generate_text_semantic(
            sentence,
            history_prompt=params['voice'],
            temp=params['temperature'],
            min_eos_p=0.05,  # this controls how likely the generation is to end
        )
        audio_array = semantic_to_waveform(semantic_tokens, history_prompt=params['voice'],)
        pieces += [audio_array, silence.copy()]
    audio = np.array(np.concatenate(pieces), dtype="float32")
    time_label = int(time.time())
    write_wav(f"extensions/bark_tts/generated/{shared.args.character}_{time_label}.wav", params['sample_rate'], audio)
    autoplay = 'autoplay' if params['autoplay'] else ''
    if params['show_text']:
        string = f'<audio src="file/extensions/bark_tts/generated/{shared.args.character}_{time_label}.wav" controls {autoplay}></audio><br>{ttstext}'
    else:
        string = f'<audio src="file/extensions/bark_tts/generated/{shared.args.character}_{time_label}.wav" controls {autoplay}></audio>'
    
    shared.args.no_stream = streaming_state
    return string


def setup():
    # tell the user what's going on
    print()
    print("== Loading Bark TTS extension ==")
    print("+ This may take a while on first run don't worry!")
    
    print("+ Creating directories (if they don't exist)...")
    if not Path("extensions/bark_tts/generated").exists():
        Path("extensions/bark_tts/generated").mkdir(parents=True)
    if not Path(model_path).exists():
        Path(model_path).mkdir(parents=True)
    print("+ Done!")
    
    # load models into extension directory so we don't clutter the pc
    print("+ Loading model...")
    if not params['force_manual_download']:
        try:
            preload_models(
                    text_use_gpu= not params['use_cpu'],
                    text_use_small= params['use_small_models'],
                    coarse_use_gpu= not params['use_cpu'],
                    coarse_use_small=params['use_small_models'],
                    fine_use_gpu= not params['use_cpu'],
                    fine_use_small=params['use_small_models'],
                    codec_use_gpu= not params['use_cpu']
                    )
        except ValueError as e:
            # for some reason the download fails sometimes, so we just do it manually
            # solution adapted from https://github.com/suno-ai/bark/issues/46
            print("\t+ Automatic download failed, trying manual download...")
            manual_model_preload()
            
    else:
        print("\t+ Forcing manual download...")
        manual_model_preload()
            
            
            
    print("+ Done!")
    
    print("== Bark TTS extension loaded ==\n\n")

def ui():
    with gr.Accordion("Bark TTS"):
        with gr.Row():
            activate = gr.Checkbox(value=params['activate'], label='Activate TTS')
            autoplay = gr.Checkbox(value=params['autoplay'], label='Autoplay')
            show_text = gr.Checkbox(value=params['show_text'], label='Show text')
            forced_speaker_enabled = gr.Checkbox(value=params['forced_speaker_enabled'], label='Forced speaker enabled')
        with gr.Row():
            forced_speaker = gr.Dropdown(forced_modes, label='Forced speaker', value=params['forced_speaker'])
            modifiers = gr.Dropdown(modifier_options, label='Modifiers', value=params['modifiers'], multiselect=True)
            voice = gr.Dropdown(voice_presets, label='Voice Preset', value=params['voice'])
        with gr.Row():
            sample_rate = gr.Slider(minimum=18000, maximum=30000, value=params['sample_rate'], label='Sample Rate')
            temperature = gr.Slider(minimum=0.1, maximum=1.0, value=params['temperature'], label='Temperature')
      
    activate.change(lambda x: params.update({'activate': x}), activate, None)
    autoplay.change(lambda x: params.update({'autoplay': x}), autoplay, None)
    show_text.change(lambda x: params.update({'show_text': x}), show_text, None)
    forced_speaker_enabled.change(lambda x: params.update({'forced_speaker_enabled': x}), forced_speaker_enabled, None)      
    forced_speaker.change(lambda x: params.update({'forced_speaker': x}), forced_speaker, None)
    modifiers.change(lambda x: params.update({'modifiers': x}), modifiers, None)
    voice.change(lambda x: params.update({'voice': x}), voice, None)
    sample_rate.change(lambda x: params.update({'sample_rate': x}), sample_rate, None)
    temperature.change(lambda x: params.update({'temperature': x}), temperature, None)
