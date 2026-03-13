#!/usr/bin/env python3
"""
ElevenLabs TTS ボイス生成ツール - GUI版
台本CSVを選択して ElevenLabs API でボイスを生成する
"""

import csv
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

# スクリプトと同じフォルダを作業ディレクトリにする（.env / config.json の読み込みに必要）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# csv_split_tool の除外キャラリスト
EXCLUDE_NAMES = ['霊夢', '魔理沙', 'ブルアカ霊夢', 'ブルアカ魔理沙', '場面転換', 'アイキャッチ']


def read_csv_rows(filepath: str) -> list[dict]:
    """CSVを読んで [{serial, character, text}, ...] を返す。"""
    rows = []
    with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        next(reader, None)  # ヘッダースキップ
        for row in reader:
            if len(row) < 3:
                continue
            try:
                serial = int(row[0])
            except ValueError:
                continue
            rows.append({
                'serial': serial,
                'character': row[1].strip(),
                'text': row[2].strip(),
            })
    return rows


def check_csv_alignment(split_path: str, elevenlabs_path: str) -> list[str]:
    """_split.csv と _elevenlabs.csv の整合性をチェックし、結果メッセージのリストを返す。"""
    split_rows = read_csv_rows(split_path)
    el_rows = read_csv_rows(elevenlabs_path)

    messages = []
    messages.append(f"台本CSV（split）: {len(split_rows)}行")
    messages.append(f"ボイスCSV（elevenlabs）: {len(el_rows)}行")

    if len(split_rows) != len(el_rows):
        messages.append(f"⚠ 行数が一致しません！ (差: {abs(len(split_rows) - len(el_rows))}行)")

    mismatches = []
    max_rows = min(len(split_rows), len(el_rows))
    for i in range(max_rows):
        s = split_rows[i]
        e = el_rows[i]
        problems = []
        if s['serial'] != e['serial']:
            problems.append(f"連番: {s['serial']}→{e['serial']}")
        if s['character'] != e['character']:
            problems.append(f"キャラ: {s['character']}→{e['character']}")
        if problems:
            mismatches.append(f"  行{i+1}: {', '.join(problems)}")

    if mismatches:
        messages.append(f"⚠ {len(mismatches)}件の不一致:")
        messages.extend(mismatches[:20])
        if len(mismatches) > 20:
            messages.append(f"  ...他 {len(mismatches) - 20}件")
    else:
        if len(split_rows) == len(el_rows):
            messages.append("✓ 整合性OK: 連番・キャラ名すべて一致")
        else:
            messages.append("✓ 共通範囲の連番・キャラ名は一致（行数差あり）")

    return messages



def load_config() -> dict:
    config_path = os.path.join(BASE_DIR, 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def split_csv(input_path: str) -> tuple[list[list], int, int]:
    """CSV分割ツールと同じロジックでCSVを分割する。

    Returns:
        (rows, split_count, exclude_count)
        rows[0] はヘッダー行（連番列を先頭に追加済み）
    """
    rows = []
    split_count = 0
    exclude_count = 0
    serial_number = 1

    with open(input_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows.append(['連番'] + header)

        for row in reader:
            if not row or not row[0].strip():
                continue

            char_name = row[0].strip()

            if '\n' in char_name:
                characters = [c.strip() for c in char_name.split('\n') if c.strip()]
                if len(characters) > 1:
                    serif = row[1] if len(row) > 1 else ''
                    rest = row[2:] if len(row) > 2 else []
                    for char in characters:
                        if char in EXCLUDE_NAMES:
                            exclude_count += 1
                            continue
                        rows.append([str(serial_number), char, serif] + rest)
                        serial_number += 1
                    split_count += 1
                    continue

            if char_name in EXCLUDE_NAMES:
                exclude_count += 1
                continue

            new_row = [char_name] + row[1:]
            rows.append([str(serial_number)] + new_row)
            serial_number += 1

    return rows, split_count, exclude_count


class ElevenLabsGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ElevenLabs ボイス生成ツール")
        self.root.geometry("540x480")
        self.root.minsize(480, 420)

        self.config = load_config()
        # config.json の voice_base_dir_win をボイス出力のベースフォルダとして使う
        self.voice_base_dir = self.config.get('ymm4', {}).get(
            'voice_base_dir_win', os.path.join(BASE_DIR, 'output')
        )
        self.split_csv_path = ''  # STEP 1 で生成した _split.csv のパス

        self.setup_ui()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="ElevenLabs ボイス生成ツール", font=('', 12, 'bold')).pack(pady=(0, 12))

        # ── STEP 1: 原本CSV → 分割 ──────────────────────────────
        step1_frame = ttk.LabelFrame(main_frame, text="STEP 1: 原本CSVを分割して保存", padding="8")
        step1_frame.pack(fill=tk.X, pady=(0, 8))

        src_row = ttk.Frame(step1_frame)
        src_row.pack(fill=tk.X)
        ttk.Label(src_row, text="原本CSV:", width=10).pack(side=tk.LEFT)
        self.src_var = tk.StringVar()
        src_entry = ttk.Entry(src_row, textvariable=self.src_var)
        src_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(src_row, text="参照", command=self.browse_src, width=6).pack(side=tk.LEFT)
        self._register_drop(src_entry, self.src_var, is_file=True)

        ttk.Button(step1_frame, text="分割して保存", command=self.split_and_save, width=16).pack(pady=(8, 0))

        # ── STEP 1.5: Claudeで変換 ──────────────────────────────
        step15_frame = ttk.LabelFrame(main_frame, text="STEP 1.5: Claudeで台本変換（任意）", padding="8")
        step15_frame.pack(fill=tk.X, pady=(0, 8))

        prompt_row = ttk.Frame(step15_frame)
        prompt_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(prompt_row, text="プロンプト:", width=10).pack(side=tk.LEFT)
        self.prompt_path_var = tk.StringVar(value=self.config.get('claude_prompt_path', ''))
        ttk.Entry(prompt_row, textvariable=self.prompt_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(prompt_row, text="参照", command=self.browse_prompt, width=6).pack(side=tk.LEFT)

        btn_row = ttk.Frame(step15_frame)
        btn_row.pack(fill=tk.X)
        self.claude_btn = ttk.Button(btn_row, text="台本をコピー", command=self.claude_convert, width=14)
        self.claude_btn.pack(side=tk.LEFT)
        self.claude_load_btn = ttk.Button(btn_row, text="結果を読み込む", command=self.claude_load,
                                          width=14, state=tk.DISABLED)
        self.claude_load_btn.pack(side=tk.LEFT, padx=(5, 0))
        self.claude_out_label = ttk.Label(btn_row, text="", foreground="gray")
        self.claude_out_label.pack(side=tk.LEFT, padx=(8, 0))

        # ── STEP 2: ボイス生成 ──────────────────────────────────
        step2_frame = ttk.LabelFrame(main_frame, text="STEP 2: ボイス生成", padding="8")
        step2_frame.pack(fill=tk.X, pady=(0, 8))

        script_row = ttk.Frame(step2_frame)
        script_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(script_row, text="台本CSV:", width=10).pack(side=tk.LEFT)
        self.script_var = tk.StringVar()
        script_entry = ttk.Entry(script_row, textvariable=self.script_var)
        script_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(script_row, text="参照", command=self.browse_script, width=6).pack(side=tk.LEFT)
        self._register_drop(script_entry, self.script_var, is_file=True)

        output_row = ttk.Frame(step2_frame)
        output_row.pack(fill=tk.X)
        ttk.Label(output_row, text="出力フォルダ:", width=10).pack(side=tk.LEFT)
        self.output_var = tk.StringVar()
        ttk.Entry(output_row, textvariable=self.output_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(output_row, text="参照", command=self.browse_output, width=6).pack(side=tk.LEFT)

        gen_row = ttk.Frame(step2_frame)
        gen_row.pack(pady=(8, 0))
        self.check_btn = ttk.Button(gen_row, text="整合性チェック", command=self.check_alignment, width=14)
        self.check_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.generate_btn = ttk.Button(gen_row, text="ボイス生成", command=self.generate, width=14)
        self.generate_btn.pack(side=tk.LEFT)

        # ── ログ ────────────────────────────────────────────────
        status_frame = ttk.LabelFrame(main_frame, text="ステータス", padding="5")
        status_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(status_frame, height=8, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # ── ブラウズ ─────────────────────────────────────────────────

    def browse_src(self):
        initial = self.src_var.get()
        if initial:
            initial = os.path.dirname(initial)
        else:
            initial = self.voice_base_dir
        path = filedialog.askopenfilename(
            title="原本CSVを選択",
            initialdir=initial,
            filetypes=[("CSVファイル", "*.csv"), ("すべてのファイル", "*.*")],
        )
        if path:
            self.src_var.set(path)

    def browse_script(self):
        path = filedialog.askopenfilename(
            title="台本CSVを選択",
            filetypes=[("台本ファイル", "*.csv *.txt"), ("CSVファイル", "*.csv"),
                       ("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")],
        )
        if not path:
            return
        self.script_var.set(path)
        # 出力フォルダを自動設定
        self._set_output_from_script(path)

    def browse_prompt(self):
        path = filedialog.askopenfilename(
            title="プロンプトファイルを選択",
            filetypes=[("Markdownファイル", "*.md"), ("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")],
        )
        if path:
            self.prompt_path_var.set(path)

    def browse_output(self):
        initial = self.output_var.get() or self.voice_base_dir
        path = filedialog.askdirectory(title="出力フォルダを選択", initialdir=initial)
        if path:
            self.output_var.set(path)

    def _set_output_from_script(self, script_path: str):
        """台本CSVのステムからプロジェクトフォルダを出力先に設定する。"""
        stem = os.path.splitext(os.path.basename(script_path))[0]
        # _split サフィックスを除いてプロジェクト名を取得
        project = stem.removesuffix('_split')
        self.output_var.set(os.path.join(self.voice_base_dir, project))

    # ── 分割して保存 ─────────────────────────────────────────────

    def split_and_save(self):
        src_path = self.src_var.get().strip()
        if not src_path:
            messagebox.showerror("エラー", "原本CSVを選択してください")
            return
        if not os.path.exists(src_path):
            messagebox.showerror("エラー", f"ファイルが見つかりません:\n{src_path}")
            return

        stem = os.path.splitext(os.path.basename(src_path))[0]
        project_dir  = os.path.join(self.voice_base_dir, stem)
        script_dir   = os.path.join(project_dir, '台本')
        voice_dir    = os.path.join(project_dir, 'ボイス')
        split_path   = os.path.join(script_dir, f"{stem}_split.csv")

        os.makedirs(script_dir, exist_ok=True)
        os.makedirs(voice_dir, exist_ok=True)

        try:
            rows, split_count, exclude_count = split_csv(src_path)
        except Exception as e:
            messagebox.showerror("エラー", f"CSV分割に失敗しました:\n{e}")
            return

        with open(split_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)

        data_rows = len(rows) - 1
        self.log(f"分割完了: {data_rows}行  (分割:{split_count}行, 除外:{exclude_count}行)")
        self.log(f"保存先: {split_path}")

        # STEP 2 を自動入力
        self.split_csv_path = split_path
        self.script_var.set(split_path)
        self.output_var.set(voice_dir)

        messagebox.showinfo("完了",
            f"CSV分割完了!\n\n"
            f"出力行数: {data_rows}\n"
            f"分割: {split_count}行  除外: {exclude_count}行\n\n"
            f"台本CSV:\n{split_path}\n\n"
            f"出力フォルダ:\n{voice_dir}"
        )

    # ── ボイス生成 ───────────────────────────────────────────────

    def generate(self):
        script_path = self.script_var.get().strip()
        output_dir  = self.output_var.get().strip()

        if not script_path:
            messagebox.showerror("エラー", "台本CSVを選択してください")
            return
        if not os.path.exists(script_path):
            messagebox.showerror("エラー", f"ファイルが見つかりません:\n{script_path}")
            return
        if not output_dir:
            messagebox.showerror("エラー", "出力フォルダを指定してください")
            return

        self.generate_btn.config(state=tk.DISABLED)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

        thread = threading.Thread(
            target=self._generate_thread, args=(script_path, output_dir), daemon=True
        )
        thread.start()

    def _generate_thread(self, script_path: str, output_dir: str):
        try:
            from dotenv import load_dotenv
            from elevenlabs.client import ElevenLabs
            from generate import (
                process_dialogues, fetch_available_voices,
                check_missing_voices, load_config as gen_load_config,
            )
            from parser import parse_from_file

            load_dotenv(os.path.join(BASE_DIR, '.env'))

            api_key = os.getenv("ELEVENLABS_API_KEY")
            if not api_key:
                self._thread_safe_log("エラー: ELEVENLABS_API_KEY が .env に設定されていません")
                self.root.after(0, lambda: messagebox.showerror(
                    "エラー", ".env に ELEVENLABS_API_KEY を設定してください"))
                return

            config = gen_load_config(os.path.join(BASE_DIR, 'config.json'))
            client = ElevenLabs(api_key=api_key)

            self._thread_safe_log(f"台本: {script_path}")
            self._thread_safe_log(f"出力先: {output_dir}")
            self._thread_safe_log("")

            dialogues = parse_from_file(script_path)
            if not dialogues:
                self._thread_safe_log("エラー: セリフが見つかりませんでした")
                self.root.after(0, lambda: messagebox.showerror(
                    "エラー", "台本からセリフを解析できませんでした"))
                return

            self._thread_safe_log(f"{len(dialogues)} 件のセリフを検出しました")

            # 未設定キャラのチェック
            self._thread_safe_log("ボイス設定を確認中...")
            available_voices = fetch_available_voices(client)
            missing = check_missing_voices(dialogues, config, available_voices)

            if missing:
                addable     = [m for m in missing if m["suggested_voice_id"]]
                not_addable = [m for m in missing if not m["suggested_voice_id"]]

                if addable:
                    for m in addable:
                        config["character_voices"][m["character"]] = m["suggested_voice_id"]
                    with open(os.path.join(BASE_DIR, 'config.json'), 'w', encoding='utf-8') as f:
                        json.dump(config, f, ensure_ascii=False, indent=4)
                    names = ", ".join(m["character"] for m in addable)
                    self._thread_safe_log(f"config.json に自動追加: {names}")

                if not_addable:
                    for m in not_addable:
                        self._thread_safe_log(f"  スキップ: {m['character']} ({m['count']}件)")
                    names = "\n".join(f"  - {m['character']} ({m['count']}件)" for m in not_addable)
                    proceed = self._ask_proceed(
                        "未設定キャラあり",
                        f"以下のキャラは voice_id 未設定のためスキップされます:\n{names}\n\n続けますか？"
                    )
                    if not proceed:
                        self._thread_safe_log("キャンセルしました")
                        return

            # generate の print を GUI ログに転送
            import builtins
            original_print = builtins.print

            def gui_print(*args, **kwargs):
                self._thread_safe_log(" ".join(str(a) for a in args))

            builtins.print = gui_print
            try:
                results = process_dialogues(dialogues, config, client, output_dir)
            finally:
                builtins.print = original_print

            success = sum(1 for r in results if r["status"] == "success")
            skipped = sum(1 for r in results if r["status"] == "skipped")
            errors  = sum(1 for r in results if r["status"] == "error")

            self._thread_safe_log(f"\n--- 完了 ---")
            self._thread_safe_log(f"成功: {success}  スキップ: {skipped}  エラー: {errors}")
            self._thread_safe_log(f"出力先: {output_dir}")

            self.root.after(0, lambda: messagebox.showinfo(
                "完了",
                f"ボイス生成完了!\n\n"
                f"成功: {success}\nスキップ: {skipped}\nエラー: {errors}\n\n"
                f"出力先:\n{output_dir}"
            ))

        except Exception as e:
            self._thread_safe_log(f"エラー: {e}")
            self.root.after(0, lambda: messagebox.showerror("エラー", str(e)))
        finally:
            self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL))

    def log(self, message: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def _thread_safe_log(self, message: str):
        self.root.after(0, lambda m=message: self.log(m))

    def _register_drop(self, widget, var: tk.StringVar, is_file: bool = True):
        if not _DND_AVAILABLE:
            return
        widget.drop_target_register(DND_FILES)
        def on_drop(event):
            path = event.data.strip()
            # Windows: パスに空白がある場合 {} で囲まれる
            if path.startswith('{') and path.endswith('}'):
                path = path[1:-1]
            var.set(path)
            if is_file and path.lower().endswith('.csv'):
                self._on_src_changed(path)
        widget.dnd_bind('<<Drop>>', on_drop)

    # ── Claude変換 ───────────────────────────────────────────────

    def claude_convert(self):
        script_path = self.script_var.get().strip()
        if not script_path or not os.path.exists(script_path):
            messagebox.showerror("エラー", "先にSTEP 1で台本CSVを生成してください")
            return

        # 台本CSV → キャラ名\tセリフ 形式に変換
        lines = []
        with open(script_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.reader(f)
            next(reader, None)  # ヘッダースキップ
            for row in reader:
                if len(row) >= 3:
                    lines.append(f"{row[1]}\t{row[2]}")
        input_text = "\n".join(lines)

        # クリップボードにコピー
        self.root.clipboard_clear()
        self.root.clipboard_append(input_text)

        # 変換結果の保存先パスを計算して表示
        stem = os.path.splitext(os.path.basename(script_path))[0]
        stem = stem.removesuffix('_split')
        out_dir = os.path.dirname(script_path)
        self._claude_out_path = os.path.join(out_dir, f"{stem}_claude.txt")

        self.claude_out_label.config(
            text=f"→ {os.path.basename(self._claude_out_path)} に保存後「読み込む」",
            foreground="blue"
        )
        self.claude_load_btn.config(state=tk.NORMAL)
        self.log(f"クリップボードにコピーしました ({len(lines)}行)")
        self.log(f"Claude Codeで変換後、以下に保存してください:")
        self.log(f"  {self._claude_out_path}")

    def claude_load(self):
        path = self._claude_out_path if hasattr(self, '_claude_out_path') else ''
        if not path or not os.path.exists(path):
            messagebox.showerror("エラー", f"ファイルが見つかりません:\n{path}\n\nClaude Codeの変換結果を保存してください")
            return
        self.script_var.set(path)
        self.claude_out_label.config(text="読み込み完了", foreground="green")
        self.log(f"台本を更新: {path}")

    # ── 整合性チェック ─────────────────────────────────────────────

    def check_alignment(self):
        """_split.csv と台本CSV（_elevenlabs.csv）の整合性をチェック"""
        elevenlabs_path = self.script_var.get().strip()
        if not elevenlabs_path or not os.path.exists(elevenlabs_path):
            messagebox.showerror("エラー", "台本CSVを選択してください")
            return

        # split_csv_path が未設定の場合、同じフォルダ内の _split.csv を探す
        split_path = self.split_csv_path
        if not split_path or not os.path.exists(split_path):
            # 台本CSVと同じフォルダで _split.csv を検索
            csv_dir = os.path.dirname(elevenlabs_path)
            for f in os.listdir(csv_dir):
                if f.endswith('_split.csv'):
                    split_path = os.path.join(csv_dir, f)
                    break

        if not split_path or not os.path.exists(split_path):
            messagebox.showerror("エラー",
                "_split.csv が見つかりません。\n先にSTEP 1でCSVを分割してください。")
            return

        # 同じファイルを比較しても意味がない
        if os.path.normpath(split_path) == os.path.normpath(elevenlabs_path):
            messagebox.showinfo("チェック",
                "台本CSVが _split.csv と同じファイルです。\n"
                "Claude変換後のCSVをSTEP 2に設定してからチェックしてください。")
            return

        results = check_csv_alignment(split_path, elevenlabs_path)

        self.log("\n--- 整合性チェック ---")
        self.log(f"比較元: {os.path.basename(split_path)}")
        self.log(f"比較先: {os.path.basename(elevenlabs_path)}")
        for msg in results:
            self.log(msg)

        # 結果をダイアログでも表示
        summary = "\n".join(results)
        has_warning = any("⚠" in m for m in results)
        if has_warning:
            messagebox.showwarning("整合性チェック", summary)
        else:
            messagebox.showinfo("整合性チェック", summary)

    def _on_src_changed(self, path: str):
        """原本CSVがセットされたとき台本CSV・出力フォルダを自動補完"""
        pass  # browse_src の既存ロジックは手動参照のみ対象のため、必要に応じて拡張

    def _ask_proceed(self, title: str, message: str) -> bool:
        result = [False]
        event = threading.Event()

        def show():
            result[0] = messagebox.askyesno(title, message)
            event.set()

        self.root.after(0, show)
        event.wait()
        return result[0]


def main():
    root = TkinterDnD.Tk() if _DND_AVAILABLE else tk.Tk()
    app = ElevenLabsGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
