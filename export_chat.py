"""Достаёт один чат из экспорта claude.ai и сохраняет его в Markdown для бота.

Экспорт: claude.ai → Settings → Privacy → Export data. На почту придёт ссылка на zip-архив,
внутри которого лежит conversations.json. Скрипт принимает и сам zip, и conversations.json.

Примеры:
    python export_chat.py data-export.zip --list
    python export_chat.py data-export.zip --name "моделирование"
    python export_chat.py conversations.json --uuid 1b2c... -o context/chat.md
"""

import argparse
import json
import sys
import zipfile
from pathlib import Path


def load_conversations(path: Path) -> list[dict]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            name = next(n for n in zf.namelist() if n.endswith("conversations.json"))
            return json.loads(zf.read(name))
    return json.loads(path.read_text(encoding="utf-8"))


def render_block(block: dict) -> str:
    kind = block.get("type")
    if kind == "text":
        return block.get("text", "")
    if kind == "tool_use":
        # Артефакты claude.ai (код, документы) приходят как tool_use с полем content.
        data = block.get("input") or {}
        if isinstance(data, dict) and data.get("content"):
            title = data.get("title") or data.get("id") or block.get("name", "artifact")
            lang = data.get("language", "")
            return f"[Артефакт: {title}]\n```{lang}\n{data['content']}\n```"
        return f"[Инструмент {block.get('name')}]\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"
    if kind == "tool_result":
        parts = block.get("content") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        return "[Результат инструмента]\n" + "\n".join(texts) if texts else ""
    # thinking и прочие служебные блоки пропускаем.
    return ""


def render_message(msg: dict) -> str:
    author = "Преподаватель" if msg.get("sender") == "human" else "Claude"
    blocks = msg.get("content") or []
    body = "\n\n".join(filter(None, (render_block(b) for b in blocks))) or msg.get("text", "")

    extras = []
    for att in msg.get("attachments") or []:
        name = att.get("file_name", "вложение")
        content = att.get("extracted_content")
        extras.append(f"[Вложение: {name}]\n```\n{content}\n```" if content else f"[Вложение: {name}]")
    for f in msg.get("files") or []:
        extras.append(f"[Файл: {f.get('file_name', '?')} — содержимое в экспорт не попадает]")

    return "\n\n".join([f"## {author}", body.strip(), *extras]).strip()


def render_conversation(conv: dict) -> str:
    header = f"# {conv.get('name') or 'Без названия'}\n\nДата: {conv.get('created_at', '')[:10]}"
    messages = [render_message(m) for m in conv.get("chat_messages", [])]
    return "\n\n---\n\n".join([header, *messages]) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("export", type=Path, help="zip-архив экспорта или conversations.json")
    parser.add_argument("--list", action="store_true", help="показать список чатов")
    parser.add_argument("--name", help="часть названия чата (без учёта регистра)")
    parser.add_argument("--uuid", help="uuid чата (из --list)")
    parser.add_argument("-o", "--output", type=Path, default=Path("context/chat.md"))
    args = parser.parse_args()

    conversations = load_conversations(args.export)

    if args.list or not (args.name or args.uuid):
        for c in sorted(conversations, key=lambda c: c.get("updated_at", ""), reverse=True):
            print(f"{c['uuid']}  {c.get('updated_at', '')[:10]}  "
                  f"{len(c.get('chat_messages', [])):>4} сообщ.  {c.get('name') or '—'}")
        return

    if args.uuid:
        matches = [c for c in conversations if c["uuid"].startswith(args.uuid)]
    else:
        matches = [c for c in conversations if args.name.lower() in (c.get("name") or "").lower()]

    if len(matches) != 1:
        print(f"Найдено чатов: {len(matches)}. Уточните --name или используйте --uuid:", file=sys.stderr)
        for c in matches:
            print(f"  {c['uuid']}  {c.get('name')}", file=sys.stderr)
        sys.exit(1)

    text = render_conversation(matches[0])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Сохранено: {args.output} ({len(text):,} символов, «{matches[0].get('name')}»)")


if __name__ == "__main__":
    main()
