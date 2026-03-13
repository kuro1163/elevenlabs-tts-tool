import sys, os, json
sys.path.insert(0, 'D:/cursor/elevenlabs-tts-tool')
os.chdir('D:/cursor/elevenlabs-tts-tool')
from dotenv import load_dotenv
load_dotenv()

from elevenlabs.client import ElevenLabs

targets = ['シロコ', 'セリカ', 'ノノミ', 'アロナ', 'アヤネ', 'プラナ',
           'ゲヘモブA', 'セナ', 'ゲヘモブB', 'アイキャッチ']

api_key = os.getenv('ELEVENLABS_API_KEY')
client = ElevenLabs(api_key=api_key)
response = client.voices.get_all()
available = {v.name: v.voice_id for v in response.voices}

print('ElevenLabs に存在するボイス:')
found = {}
not_found = []
for name in targets:
    if name in available:
        found[name] = available[name]
        print(f'  [OK] {name}: {available[name]}')
    else:
        not_found.append(name)
        print(f'  [NG] {name}: 見つかりません')

if found:
    config_path = 'D:/cursor/elevenlabs-tts-tool/config.json'
    with open(config_path, encoding='utf-8') as f:
        config = json.load(f)
    config['character_voices'].update(found)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    print(f'\n{len(found)}件を config.json に追加しました')
