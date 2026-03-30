#!/usr/bin/env python3
"""
ElevenLabs ボイスデザイン & ボイスリミックスツール - GUI版
"""

import json
import os
import random
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox, scrolledtext, filedialog

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # gui/ の1つ上がプロジェクトルート
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.config import load_config, save_config
from core.client import get_client as get_elevenlabs_client

VOICE_LOG_PATH = os.path.join(BASE_DIR, "voice_design_log.jsonl")


def append_voice_log(entry: dict):
    """ボイスデザイン/リミックスの操作ログをJSONLファイルに追記"""
    entry["timestamp"] = datetime.now().isoformat()
    with open(VOICE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def make_scrollable_frame(parent) -> tuple[tk.Canvas, ttk.Frame]:
    """親フレーム内にスクロール可能なフレームを作成して返す"""
    canvas = tk.Canvas(parent, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
    inner = ttk.Frame(canvas, padding="15")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=inner, anchor="nw", tags="inner")
    canvas.configure(yscrollcommand=scrollbar.set)
    # 幅を追従させる
    canvas.bind("<Configure>", lambda e: canvas.itemconfig("inner", width=e.width))
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    # マウスホイール
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    return canvas, inner


# ══════════════════════════════════════════════════════════════════════════════
# ボイスデザイン タブ
# ══════════════════════════════════════════════════════════════════════════════

class VoiceDesignTab:
    def __init__(self, notebook, log_func):
        self.log = log_func
        self.previews: list[dict] = []
        self.selected_idx: int | None = None

        frame = ttk.Frame(notebook)
        notebook.add(frame, text="ボイスデザイン")
        self._canvas, main = make_scrollable_frame(frame)
        self._build(main)

    def _build(self, main):
        # ── ボイス説明 ──────────────────────────────────────────
        ttk.Label(main, text="ボイス説明（英語推奨）:").pack(anchor=tk.W)
        self.desc_text = tk.Text(main, height=4, wrap=tk.WORD)
        self.desc_text.pack(fill=tk.X, pady=(2, 8))
        self.desc_text.insert('1.0', '')

        # ── サンプルテキスト ────────────────────────────────────
        ttk.Label(main, text="サンプルテキスト（空欄で自動生成 / 100文字以上）:").pack(anchor=tk.W)
        self.sample_text = tk.Text(main, height=7, wrap=tk.WORD)
        self.sample_text.pack(fill=tk.X, pady=(2, 8))
        self.sample_text.insert('1.0',
            'こんにちは先生！今日はいい天気ですね！先生？その本は何ですか！！！'
            '私は今日はシャーレの当番に来ました。よろしくお願いします！'
            '赤字覚悟の大セールですよ～。見ていってください！'
            'あれっ？先生どうかしましたか？変ですよ！'
        )

        # ── プロンプト強度 ──────────────────────────────────────
        gs_row = ttk.Frame(main)
        gs_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(gs_row, text="プロンプト強度:").pack(side=tk.LEFT)
        self.guidance_var = tk.DoubleVar(value=2.0)
        ttk.Scale(gs_row, from_=0.0, to=15.0, variable=self.guidance_var,
                  orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=(8, 5))
        self.guidance_label = ttk.Label(gs_row, text="2.0", width=5)
        self.guidance_label.pack(side=tk.LEFT)
        ttk.Label(gs_row, text="(低=自由 / 高=厳密)", foreground="gray").pack(side=tk.LEFT, padx=(5, 0))
        self.guidance_var.trace_add('write', lambda *_: self.guidance_label.config(
            text=f"{self.guidance_var.get():.1f}"))

        # ── 生成数 & プレビュー生成ボタン ─────────────────────────
        gen_row = ttk.Frame(main)
        gen_row.pack(fill=tk.X, pady=(0, 10))
        self.gen_count_var = tk.IntVar(value=3)
        ttk.Radiobutton(gen_row, text="3種", variable=self.gen_count_var, value=3).pack(side=tk.LEFT)
        ttk.Radiobutton(gen_row, text="6種", variable=self.gen_count_var, value=6).pack(side=tk.LEFT, padx=(8, 0))
        self.preview_btn = ttk.Button(gen_row, text="プレビューを生成",
                                      command=self.generate_previews, width=18)
        self.preview_btn.pack(side=tk.LEFT, padx=(15, 0))

        # ── プレビュー一覧 ──────────────────────────────────────
        preview_frame = ttk.LabelFrame(main, text="プレビュー", padding="8")
        preview_frame.pack(fill=tk.X, pady=(0, 10))

        self.preview_rows: list[dict] = []
        for i in range(6):
            row = ttk.Frame(preview_frame)
            row.pack(fill=tk.X, pady=3)
            lbl = ttk.Label(row, text=f"#{i+1} ---", width=36, anchor=tk.W)
            lbl.pack(side=tk.LEFT)
            play_btn = ttk.Button(row, text="▶ 再生", width=8,
                                  command=lambda idx=i: self.play_preview(idx),
                                  state=tk.DISABLED)
            play_btn.pack(side=tk.LEFT, padx=(5, 5))
            select_btn = ttk.Button(row, text="これを使う", width=10,
                                    command=lambda idx=i: self.select_preview(idx),
                                    state=tk.DISABLED)
            select_btn.pack(side=tk.LEFT)
            self.preview_rows.append({'label': lbl, 'play': play_btn, 'select': select_btn})
            if i >= 3:
                row.pack_forget()
        self.gen_count_var.trace_add('write', self._on_gen_count_change)

        # ── 保存フォーム ────────────────────────────────────────
        save_frame = ttk.LabelFrame(main, text="ボイスを保存してconfig.jsonに登録", padding="8")
        save_frame.pack(fill=tk.X, pady=(0, 10))

        name_row = ttk.Frame(save_frame)
        name_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(name_row, text="キャラ名:", width=10).pack(side=tk.LEFT)
        self.char_name_var = tk.StringVar()
        ttk.Entry(name_row, textvariable=self.char_name_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.selected_label = ttk.Label(save_frame, text="選択中: なし", foreground="gray")
        self.selected_label.pack(anchor=tk.W, pady=(0, 5))

        self.save_btn = ttk.Button(save_frame, text="保存してconfig.jsonに登録",
                                   command=self.save_voice, width=26, state=tk.DISABLED)
        self.save_btn.pack()

    def _on_gen_count_change(self, *_):
        count = self.gen_count_var.get()
        for i, row_data in enumerate(self.preview_rows):
            row_widget = row_data['label'].master
            if i < count:
                row_widget.pack(fill=tk.X, pady=3)
            else:
                row_widget.pack_forget()

    # ── プレビュー生成 ──────────────────────────────────────────

    def generate_previews(self):
        desc = self.desc_text.get('1.0', tk.END).strip()
        if not desc:
            messagebox.showerror("エラー", "ボイス説明を入力してください")
            return
        if len(desc) > 1000:
            messagebox.showerror("エラー", f"ボイス説明が長すぎます（{len(desc)}文字 / 上限1000文字）")
            return
        gen_count = self.gen_count_var.get()
        self.preview_btn.config(state=tk.DISABLED)
        for i in range(gen_count):
            self.preview_rows[i]['label'].config(text="生成中...")
            self.preview_rows[i]['play'].config(state=tk.DISABLED)
            self.preview_rows[i]['select'].config(state=tk.DISABLED)
        self.previews.clear()
        self.selected_idx = None
        self.selected_label.config(text="選択中: なし")
        self.save_btn.config(state=tk.DISABLED)
        threading.Thread(target=self._generate_thread, args=(desc, gen_count), daemon=True).start()

    def _generate_thread(self, desc: str, gen_count: int):
        try:
            import base64
            client = get_elevenlabs_client()
            sample = self.sample_text.get('1.0', tk.END).strip() or None
            if sample and len(sample) < 100:
                self.log(f"サンプルテキストが{len(sample)}文字のため自動生成に切り替えます（100文字以上必要）")
                sample = None
            auto_gen = sample is None

            # 6種: 各回で説明文にユニークIDを付けて1つずつ取る（確実に全部違う声）
            self.log(f"プレビュー生成中...（{gen_count}種 / API {gen_count}回）")
            self.log(f"説明: {desc[:60]}{'...' if len(desc)>60 else ''}")

            guidance = self.guidance_var.get()
            all_previews = []
            for call_idx in range(gen_count):
                if call_idx > 0:
                    self.log(f"生成中...（{call_idx+1}/{gen_count}）")
                # 毎回異なるseedで確実に違う声を生成
                seed = random.randint(0, 2147483647)
                resp = client.text_to_voice.create_previews(
                    voice_description=desc,
                    text=sample if not auto_gen else None,
                    auto_generate_text=auto_gen,
                    guidance_scale=guidance,
                    seed=seed,
                )
                previews_data = resp.previews if hasattr(resp, 'previews') else [resp]
                if previews_data:
                    all_previews.append(previews_data[0])

            self.previews.clear()
            for i, preview in enumerate(all_previews[:gen_count]):
                audio_bytes = b""
                if hasattr(preview, 'audio_base_64') and preview.audio_base_64:
                    try:
                        audio_bytes = base64.b64decode(preview.audio_base_64)
                    except Exception as e:
                        self.log(f"  base64デコード失敗: {e}")

                tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False,
                                                  prefix=f'voice_preview_{i}_')
                tmp.write(audio_bytes)
                tmp.close()

                vid = getattr(preview, 'generated_voice_id', f'preview_{i}')
                self.previews.append({'generated_voice_id': vid,
                                      'audio_bytes': audio_bytes,
                                      'temp_path': tmp.name})

                def update_row(idx=i, voice_id=vid):
                    self.preview_rows[idx]['label'].config(text=f"#{idx+1} {voice_id[:24]}...")
                    self.preview_rows[idx]['play'].config(state=tk.NORMAL)
                    self.preview_rows[idx]['select'].config(state=tk.NORMAL)
                self.preview_rows[i]['label'].winfo_toplevel().after(0, update_row)
                self.log(f"  #{i+1} 生成完了: {vid[:24]}...")

            self.log(f"{len(self.previews)}件のプレビューを生成しました")
        except Exception as e:
            self.log(f"エラー: {e}")
            messagebox.showerror("エラー", str(e))
        finally:
            self.preview_rows[0]['play'].winfo_toplevel().after(
                0, lambda: self.preview_btn.config(state=tk.NORMAL))

    def play_preview(self, idx: int):
        if idx >= len(self.previews):
            return
        path = self.previews[idx]['temp_path']
        if not os.path.exists(path):
            messagebox.showerror("エラー", "音声ファイルが見つかりません")
            return
        os.startfile(path)

    def select_preview(self, idx: int):
        if idx >= len(self.previews):
            return
        self.selected_idx = idx
        vid = self.previews[idx]['generated_voice_id']
        self.selected_label.config(text=f"選択中: #{idx+1}  ({vid[:28]}...)", foreground="blue")
        self.save_btn.config(state=tk.NORMAL)
        self.log(f"#{idx+1} を選択しました")

    def save_voice(self):
        char_name = self.char_name_var.get().strip()
        if not char_name:
            messagebox.showerror("エラー", "キャラ名を入力してください")
            return
        if self.selected_idx is None:
            messagebox.showerror("エラー", "プレビューを選択してください")
            return
        old_voice_id = None
        config = load_config()
        if char_name in config.get('character_voices', {}):
            old_voice_id = config['character_voices'][char_name]
            if not messagebox.askyesno(
                "上書き確認",
                f'"{char_name}" は既に登録されています。\n\n'
                f'既存voice_id: {old_voice_id}\n\n'
                f'上書きしますか？\n（ElevenLabs側の旧ボイスも削除されます）'):
                return
        self.save_btn.config(state=tk.DISABLED)
        desc = self.desc_text.get('1.0', tk.END).strip()
        vid = self.previews[self.selected_idx]['generated_voice_id']
        threading.Thread(target=self._save_thread, args=(char_name, desc, vid, old_voice_id), daemon=True).start()

    def _save_thread(self, char_name: str, desc: str, generated_voice_id: str, old_voice_id: str | None = None):
        try:
            client = get_elevenlabs_client()
            self.log(f'ElevenLabsに保存中: "{char_name}"...')
            voice = client.text_to_voice.create(
                voice_name=char_name,
                voice_description=desc,
                generated_voice_id=generated_voice_id,
            )
            voice_id = voice.voice_id
            self.log(f"保存完了: voice_id = {voice_id}")
            # 旧ボイスをElevenLabsから削除
            if old_voice_id and old_voice_id != voice_id:
                try:
                    client.voices.delete(voice_id=old_voice_id)
                    self.log(f"旧ボイス削除: {old_voice_id}")
                except Exception as del_e:
                    self.log(f"旧ボイス削除失敗（無視）: {del_e}")
            config = load_config()
            config['character_voices'][char_name] = voice_id
            save_config(config)
            self.log(f'config.json に登録: "{char_name}" → {voice_id}')
            append_voice_log({
                "type": "design",
                "char_name": char_name,
                "voice_id": voice_id,
                "generated_voice_id": generated_voice_id,
                "prompt": desc,
                "guidance_scale": self.guidance_var.get(),
                "old_voice_id_deleted": old_voice_id,
            })
            messagebox.showinfo("登録完了", f'"{char_name}" を登録しました\n\nvoice_id: {voice_id}')
            self.char_name_var.set('')
        except Exception as e:
            self.log(f"エラー: {e}")
            messagebox.showerror("エラー", str(e))
        finally:
            self.save_btn.winfo_toplevel().after(
                0, lambda: self.save_btn.config(
                    state=tk.NORMAL if self.selected_idx is not None else tk.DISABLED))


# ══════════════════════════════════════════════════════════════════════════════
# ボイスリミックス タブ
# ══════════════════════════════════════════════════════════════════════════════

class VoiceRemixTab:
    """
    既存のボイスをテキストプロンプトで変化させる（text_to_voice.remix）
    ベースボイス + 説明 → プレビュー3種 → 選択して保存
    """
    def __init__(self, notebook, log_func):
        self.log = log_func
        self.previews: list[dict] = []
        self.selected_idx: int | None = None

        frame = ttk.Frame(notebook)
        notebook.add(frame, text="ボイスリミックス")
        self._canvas, main = make_scrollable_frame(frame)
        self._build(main)

    def _build(self, main):
        ttk.Label(main, text="既存ボイスをテキストプロンプトで変化させます",
                  foreground="gray").pack(anchor=tk.W, pady=(0, 10))

        # ── ベースボイス選択 ────────────────────────────────────
        voice_frame = ttk.LabelFrame(main, text="ベースボイス", padding="8")
        voice_frame.pack(fill=tk.X, pady=(0, 10))

        try:
            config = load_config()
            voices = config.get('character_voices', {})
            voice_names = sorted(voices.keys())
        except Exception:
            voices = {}
            voice_names = []
        self._voice_map = voices

        vrow = ttk.Frame(voice_frame)
        vrow.pack(fill=tk.X)
        self.voice_var = tk.StringVar()
        self.voice_combo = ttk.Combobox(vrow, textvariable=self.voice_var,
                                        values=voice_names, state='readonly', width=24,
                                        height=40)
        if voice_names:
            self.voice_combo.set(voice_names[0])
        self.voice_combo.pack(side=tk.LEFT)
        ttk.Button(vrow, text="更新", width=5,
                   command=self._refresh_voices).pack(side=tk.LEFT, padx=(5, 0))
        self.voice_id_label = ttk.Label(vrow, text="", foreground="gray")
        self.voice_id_label.pack(side=tk.LEFT, padx=(10, 0))
        self.voice_combo.bind('<<ComboboxSelected>>', self._on_voice_select)
        self._on_voice_select()

        # ── 変化の説明 ──────────────────────────────────────────
        ttk.Label(main, text="変化の説明（英語推奨）:").pack(anchor=tk.W)
        self.desc_text = tk.Text(main, height=4, wrap=tk.WORD)
        self.desc_text.pack(fill=tk.X, pady=(2, 8))
        self.desc_text.insert('1.0', '')

        # ── サンプルテキスト ────────────────────────────────────
        ttk.Label(main, text="サンプルテキスト（空欄で自動生成 / 100文字以上）:").pack(anchor=tk.W)
        self.sample_text = tk.Text(main, height=5, wrap=tk.WORD)
        self.sample_text.pack(fill=tk.X, pady=(2, 8))
        self.sample_text.insert('1.0',
            'こんにちは先生！今日はいい天気ですね！先生？その本は何ですか！！！'
            '私は今日はシャーレの当番に来ました。よろしくお願いします！'
            '赤字覚悟の大セールですよ～。見ていってください！'
            'あれっ？先生どうかしましたか？変ですよ！'
        )

        # ── guidance_scale（プロンプト準拠度）─────────────────────
        gs_row = ttk.Frame(main)
        gs_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(gs_row, text="プロンプト準拠度:").pack(side=tk.LEFT)
        self.guidance_var = tk.DoubleVar(value=2.0)
        ttk.Scale(gs_row, from_=0.0, to=15.0, variable=self.guidance_var,
                  orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=(8, 5))
        self.guidance_label = ttk.Label(gs_row, text="2.0", width=5)
        self.guidance_label.pack(side=tk.LEFT)
        ttk.Label(gs_row, text="(低=自由 / 高=厳密)", foreground="gray").pack(side=tk.LEFT, padx=(5, 0))
        self.guidance_var.trace_add('write', lambda *_: self.guidance_label.config(
            text=f"{self.guidance_var.get():.1f}"))

        # ── prompt_strength（変化量）──────────────────────────────
        ps_row = ttk.Frame(main)
        ps_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(ps_row, text="変化量:").pack(side=tk.LEFT)
        self.prompt_strength_var = tk.DoubleVar(value=0.5)
        ttk.Scale(ps_row, from_=0.0, to=1.0, variable=self.prompt_strength_var,
                  orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=(8, 5))
        self.ps_label = ttk.Label(ps_row, text="0.50", width=5)
        self.ps_label.pack(side=tk.LEFT)
        ttk.Label(ps_row, text="(0=元の声維持 / 1=大きく変化)", foreground="gray").pack(side=tk.LEFT, padx=(5, 0))
        self.prompt_strength_var.trace_add('write', lambda *_: self.ps_label.config(
            text=f"{self.prompt_strength_var.get():.2f}"))

        # ── 生成数 & リミックス生成ボタン ─────────────────────────
        gen_row = ttk.Frame(main)
        gen_row.pack(fill=tk.X, pady=(0, 10))
        self.gen_count_var = tk.IntVar(value=3)
        ttk.Radiobutton(gen_row, text="3種", variable=self.gen_count_var, value=3).pack(side=tk.LEFT)
        ttk.Radiobutton(gen_row, text="6種", variable=self.gen_count_var, value=6).pack(side=tk.LEFT, padx=(8, 0))
        self.remix_btn = ttk.Button(gen_row, text="リミックスを生成",
                                    command=self.generate_remix, width=18)
        self.remix_btn.pack(side=tk.LEFT, padx=(15, 0))

        # ── プレビュー一覧 ──────────────────────────────────────
        preview_frame = ttk.LabelFrame(main, text="プレビュー", padding="8")
        preview_frame.pack(fill=tk.X, pady=(0, 10))

        self.preview_rows: list[dict] = []
        for i in range(6):
            row = ttk.Frame(preview_frame)
            row.pack(fill=tk.X, pady=3)
            lbl = ttk.Label(row, text=f"#{i+1} ---", width=36, anchor=tk.W)
            lbl.pack(side=tk.LEFT)
            play_btn = ttk.Button(row, text="▶ 再生", width=8,
                                  command=lambda idx=i: self.play_preview(idx),
                                  state=tk.DISABLED)
            play_btn.pack(side=tk.LEFT, padx=(5, 5))
            select_btn = ttk.Button(row, text="これを使う", width=10,
                                    command=lambda idx=i: self.select_preview(idx),
                                    state=tk.DISABLED)
            select_btn.pack(side=tk.LEFT)
            self.preview_rows.append({'label': lbl, 'play': play_btn, 'select': select_btn})
            if i >= 3:
                row.pack_forget()
        self.gen_count_var.trace_add('write', self._on_gen_count_change)

        # ── 保存フォーム ────────────────────────────────────────
        save_frame = ttk.LabelFrame(main, text="ボイスを保存してconfig.jsonに登録", padding="8")
        save_frame.pack(fill=tk.X, pady=(0, 10))

        name_row = ttk.Frame(save_frame)
        name_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(name_row, text="キャラ名:", width=10).pack(side=tk.LEFT)
        self.char_name_var = tk.StringVar()
        ttk.Entry(name_row, textvariable=self.char_name_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.selected_label = ttk.Label(save_frame, text="選択中: なし", foreground="gray")
        self.selected_label.pack(anchor=tk.W, pady=(0, 5))

        self.save_btn = ttk.Button(save_frame, text="保存してconfig.jsonに登録",
                                   command=self.save_voice, width=26, state=tk.DISABLED)
        self.save_btn.pack()

    def _on_gen_count_change(self, *_):
        count = self.gen_count_var.get()
        for i, row_data in enumerate(self.preview_rows):
            row_widget = row_data['label'].master
            if i < count:
                row_widget.pack(fill=tk.X, pady=3)
            else:
                row_widget.pack_forget()

    def _refresh_voices(self):
        try:
            config = load_config()
            voices = config.get('character_voices', {})
            voice_names = sorted(voices.keys())
        except Exception:
            voices = {}
            voice_names = []
        self._voice_map = voices
        self.voice_combo['values'] = voice_names
        if voice_names and self.voice_var.get() not in voice_names:
            self.voice_combo.set(voice_names[0])
        self._on_voice_select()
        self.log(f"ベースボイスを更新しました（{len(voice_names)}件）")

    def _on_voice_select(self, event=None):
        name = self.voice_var.get()
        vid = self._voice_map.get(name, "")
        self.voice_id_label.config(text=vid[:32] if vid else "")

    # ── リミックス生成 ──────────────────────────────────────────

    def generate_remix(self):
        voice_name = self.voice_var.get()
        if not voice_name:
            messagebox.showerror("エラー", "ベースボイスを選択してください")
            return
        desc = self.desc_text.get('1.0', tk.END).strip()
        if not desc:
            messagebox.showerror("エラー", "変化の説明を入力してください")
            return
        if len(desc) > 1000:
            messagebox.showerror("エラー", f"変化の説明が長すぎます（{len(desc)}文字 / 上限1000文字）")
            return

        voice_id = self._voice_map.get(voice_name, "")
        if not voice_id:
            messagebox.showerror("エラー", f"voice_id が見つかりません: {voice_name}")
            return

        gen_count = self.gen_count_var.get()
        self.remix_btn.config(state=tk.DISABLED)
        for i in range(gen_count):
            self.preview_rows[i]['label'].config(text="生成中...")
            self.preview_rows[i]['play'].config(state=tk.DISABLED)
            self.preview_rows[i]['select'].config(state=tk.DISABLED)
        self.previews.clear()
        self.selected_idx = None
        self.selected_label.config(text="選択中: なし")
        self.save_btn.config(state=tk.DISABLED)

        threading.Thread(target=self._remix_thread, args=(voice_id, desc, gen_count), daemon=True).start()

    def _remix_thread(self, voice_id: str, desc: str, gen_count: int):
        try:
            import base64
            client = get_elevenlabs_client()
            sample = self.sample_text.get('1.0', tk.END).strip() or None
            if sample and len(sample) < 100:
                self.log(f"サンプルテキストが{len(sample)}文字のため自動生成に切り替えます")
                sample = None
            auto_gen = sample is None

            # 各回で説明文にユニークIDを付けて1つずつ取る（確実に全部違う声）
            self.log(f"リミックス生成中...（{gen_count}種 / API {gen_count}回）")
            self.log(f"ベース: {self.voice_var.get()} / 説明: {desc[:50]}...")

            guidance = self.guidance_var.get()
            prompt_strength = self.prompt_strength_var.get()
            all_previews = []
            for call_idx in range(gen_count):
                if call_idx > 0:
                    self.log(f"生成中...（{call_idx+1}/{gen_count}）")
                seed = random.randint(0, 2147483647)
                resp = client.text_to_voice.remix(
                    voice_id=voice_id,
                    voice_description=desc,
                    text=sample if not auto_gen else None,
                    auto_generate_text=auto_gen,
                    guidance_scale=guidance,
                    prompt_strength=prompt_strength,
                    seed=seed,
                )
                previews_data = resp.previews if hasattr(resp, 'previews') else [resp]
                if previews_data:
                    all_previews.append(previews_data[0])

            self.previews.clear()
            for i, preview in enumerate(all_previews[:gen_count]):
                audio_bytes = b""
                if hasattr(preview, 'audio_base_64') and preview.audio_base_64:
                    try:
                        audio_bytes = base64.b64decode(preview.audio_base_64)
                    except Exception as e:
                        self.log(f"  base64デコード失敗: {e}")

                tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False,
                                                  prefix=f'voice_remix_{i}_')
                tmp.write(audio_bytes)
                tmp.close()

                vid = getattr(preview, 'generated_voice_id', f'remix_{i}')
                self.previews.append({'generated_voice_id': vid,
                                      'audio_bytes': audio_bytes,
                                      'temp_path': tmp.name})

                def update_row(idx=i, voice_id=vid):
                    self.preview_rows[idx]['label'].config(text=f"#{idx+1} {voice_id[:24]}...")
                    self.preview_rows[idx]['play'].config(state=tk.NORMAL)
                    self.preview_rows[idx]['select'].config(state=tk.NORMAL)
                self.preview_rows[i]['label'].winfo_toplevel().after(0, update_row)
                self.log(f"  #{i+1} 生成完了: {vid[:24]}...")

            self.log(f"{len(self.previews)}件のリミックスを生成しました")
        except Exception as e:
            self.log(f"エラー: {e}")
            messagebox.showerror("エラー", str(e))
        finally:
            self.preview_rows[0]['play'].winfo_toplevel().after(
                0, lambda: self.remix_btn.config(state=tk.NORMAL))

    def play_preview(self, idx: int):
        if idx >= len(self.previews):
            return
        path = self.previews[idx]['temp_path']
        if not os.path.exists(path):
            messagebox.showerror("エラー", "音声ファイルが見つかりません")
            return
        os.startfile(path)

    def select_preview(self, idx: int):
        if idx >= len(self.previews):
            return
        self.selected_idx = idx
        vid = self.previews[idx]['generated_voice_id']
        self.selected_label.config(text=f"選択中: #{idx+1}  ({vid[:28]}...)", foreground="blue")
        self.save_btn.config(state=tk.NORMAL)
        self.log(f"#{idx+1} を選択しました")

    def save_voice(self):
        char_name = self.char_name_var.get().strip()
        if not char_name:
            messagebox.showerror("エラー", "キャラ名を入力してください")
            return
        if self.selected_idx is None:
            messagebox.showerror("エラー", "プレビューを選択してください")
            return
        old_voice_id = None
        config = load_config()
        if char_name in config.get('character_voices', {}):
            old_voice_id = config['character_voices'][char_name]
            if not messagebox.askyesno(
                "上書き確認",
                f'"{char_name}" は既に登録されています。\n\n'
                f'既存voice_id: {old_voice_id}\n\n'
                f'上書きしますか？\n（ElevenLabs側の旧ボイスも削除されます）'):
                return
        self.save_btn.config(state=tk.DISABLED)
        desc = self.desc_text.get('1.0', tk.END).strip()
        vid = self.previews[self.selected_idx]['generated_voice_id']
        threading.Thread(target=self._save_thread, args=(char_name, desc, vid, old_voice_id), daemon=True).start()

    def _save_thread(self, char_name: str, desc: str, generated_voice_id: str, old_voice_id: str | None = None):
        try:
            client = get_elevenlabs_client()
            self.log(f'ElevenLabsに保存中: "{char_name}"...')
            voice = client.text_to_voice.create(
                voice_name=char_name,
                voice_description=desc,
                generated_voice_id=generated_voice_id,
            )
            voice_id = voice.voice_id
            self.log(f"保存完了: voice_id = {voice_id}")
            # 旧ボイスをElevenLabsから削除
            if old_voice_id and old_voice_id != voice_id:
                try:
                    client.voices.delete(voice_id=old_voice_id)
                    self.log(f"旧ボイス削除: {old_voice_id}")
                except Exception as del_e:
                    self.log(f"旧ボイス削除失敗（無視）: {del_e}")
            config = load_config()
            config['character_voices'][char_name] = voice_id
            save_config(config)
            self.log(f'config.json に登録: "{char_name}" → {voice_id}')
            append_voice_log({
                "type": "remix",
                "char_name": char_name,
                "voice_id": voice_id,
                "generated_voice_id": generated_voice_id,
                "base_voice": self.voice_var.get(),
                "base_voice_id": self._voice_map.get(self.voice_var.get(), ""),
                "prompt": desc,
                "guidance_scale": self.guidance_var.get(),
                "prompt_strength": self.prompt_strength_var.get(),
                "old_voice_id_deleted": old_voice_id,
            })
            messagebox.showinfo("登録完了", f'"{char_name}" を登録しました\n\nvoice_id: {voice_id}')
            self.char_name_var.set('')
        except Exception as e:
            self.log(f"エラー: {e}")
            messagebox.showerror("エラー", str(e))
        finally:
            self.save_btn.winfo_toplevel().after(
                0, lambda: self.save_btn.config(
                    state=tk.NORMAL if self.selected_idx is not None else tk.DISABLED))


# ══════════════════════════════════════════════════════════════════════════════
# メインウィンドウ
# ══════════════════════════════════════════════════════════════════════════════

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ElevenLabs ボイスツール")
        self.root.geometry("600x860")
        self.root.minsize(520, 640)

        # 縦分割: 上=タブ、下=ログ（ドラッグで可変）
        paned = tk.PanedWindow(root, orient=tk.VERTICAL, sashrelief=tk.RAISED, sashwidth=5)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 10))

        tab_outer = ttk.Frame(paned)
        paned.add(tab_outer, stretch="always")

        notebook = ttk.Notebook(tab_outer)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.design_tab = VoiceDesignTab(notebook, self._log)
        self.remix_tab = VoiceRemixTab(notebook, self._log)

        # ── 共有ログ ──────────────────────────────────────────────
        log_outer = ttk.Frame(paned)
        paned.add(log_outer, stretch="never", minsize=120)

        log_frame = ttk.LabelFrame(log_outer, text="ログ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _log(self, msg: str):
        def _do():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.root.after(0, _do)


def main():
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
