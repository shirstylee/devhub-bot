import keyword
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import unicodedata

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound
from pygments.token import Comment, Keyword, Literal, Name, Number, Operator, Punctuation, String, Token

from bot.config import BASE_DIR


THEMES = {
    "seti": {
        "surface": "#151718",
        "text": "#CFD2D1",
        "keyword": "#E6CD69",
        "string": "#9FCA56",
        "comment": "#41535B",
        "number": "#CD3F45",
        "operator": "#55B5DB",
        "name": "#55B5DB",
        "punctuation": "#9FCA56",
    },
    "dracula_pro": {
        "surface": "#001F2D",
        "text": "#F8F8F2",
        "keyword": "#FF79C6",
        "string": "#F1FA8C",
        "comment": "#6272A4",
        "number": "#BD93F9",
        "operator": "#8BE9FD",
        "name": "#8BE9FD",
        "punctuation": "#F8F8F2",
    },
    "duotone": {
        "surface": "#1A1526",
        "text": "#D9D7E8",
        "keyword": "#FFB86C",
        "string": "#A3E635",
        "comment": "#7C7397",
        "number": "#A78BFA",
        "operator": "#67E8F9",
        "name": "#67E8F9",
        "punctuation": "#D9D7E8",
    },
    "hopscotch": {
        "surface": "#322931",
        "text": "#FFFFFF",
        "keyword": "#DD464C",
        "string": "#8FC13E",
        "comment": "#B33508",
        "number": "#1290BF",
        "operator": "#FD8B19",
        "name": "#1290BF",
        "punctuation": "#FFFFFF",
    },
    "lucario": {
        "surface": "#263E52",
        "text": "#F8F8F2",
        "keyword": "#FF6541",
        "string": "#E6DB74",
        "comment": "#5C98CD",
        "number": "#FFCC66",
        "operator": "#66D9EF",
        "name": "#66D9EF",
        "punctuation": "#F8F8F2",
    },
    "material": {
        "surface": "#263238",
        "text": "#EEFFFF",
        "keyword": "#C792EA",
        "string": "#C3E88D",
        "comment": "#546E7A",
        "number": "#F78C6C",
        "operator": "#89DDFF",
        "name": "#82AAFF",
        "punctuation": "#EEFFFF",
    },
    "monokai": {
        "surface": "#272822",
        "text": "#F8F8F2",
        "keyword": "#F92672",
        "string": "#E6DB74",
        "comment": "#75715E",
        "number": "#AE81FF",
        "operator": "#66D9EF",
        "name": "#A6E22E",
        "punctuation": "#F8F8F2",
    },
    "night_owl": {
        "surface": "#011627",
        "text": "#D6DEEB",
        "keyword": "#C792EA",
        "string": "#ECC48D",
        "comment": "#637777",
        "number": "#F78C6C",
        "operator": "#7FDBCA",
        "name": "#82AAFF",
        "punctuation": "#D6DEEB",
    },
    "nord": {
        "surface": "#2E3440",
        "text": "#D8DEE9",
        "keyword": "#81A1C1",
        "string": "#A3BE8C",
        "comment": "#616E88",
        "number": "#B48EAD",
        "operator": "#88C0D0",
        "name": "#8FBCBB",
        "punctuation": "#D8DEE9",
    },
    "oceanic_next": {
        "surface": "#1B2B34",
        "text": "#D8DEE9",
        "keyword": "#C594C5",
        "string": "#99C794",
        "comment": "#65737E",
        "number": "#F99157",
        "operator": "#5FB3B3",
        "name": "#6699CC",
        "punctuation": "#D8DEE9",
    },
}

BACKGROUNDS = {
    "carbon": "#ABB8C3",
    "black": "#000000",
    "navy": "#0D1224",
    "purple": "#201335",
    "transparent": None,
}


@dataclass(frozen=True)
class CodeFontBundle:
    primary: ImageFont.ImageFont
    emoji: ImageFont.ImageFont | None
    primary_codepoints: frozenset[int]
    emoji_codepoints: frozenset[int]


def create_code_screenshot(
    code: str,
    output_path: Path,
    language: str = "python",
    theme: str = "seti",
    background: str = "carbon",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    colors = THEMES.get(theme, THEMES["seti"])
    scale = 2
    fonts = _font_bundle(14 * scale)
    lines = _wrap_lines(
        _normalize_code(code).splitlines() or [""],
        fonts,
        max_width=1000 * scale,
    )

    line_height = 20 * scale
    padding_left = 18 * scale
    padding_right = 18 * scale
    padding_top = 48 * scale
    padding_bottom = 18 * scale
    max_line_width = max(_text_length(line, fonts) for line in lines)
    card_width = max(
        680 * scale,
        min(1200 * scale, max_line_width + padding_left + padding_right),
    )
    card_height = max(
        160 * scale,
        padding_top + len(lines) * line_height + padding_bottom,
    )
    outer_x = 56 * scale
    outer_y = 56 * scale
    width = card_width + outer_x * 2
    height = card_height + outer_y * 2

    bg_color = _resolve_background(background)
    image = Image.new(
        "RGBA",
        (width, height),
        (0, 0, 0, 0) if bg_color is None else bg_color,
    )
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_box = (
        outer_x,
        outer_y + 20 * scale,
        outer_x + card_width,
        outer_y + card_height + 20 * scale,
    )
    shadow_draw.rounded_rectangle(
        shadow_box,
        radius=5 * scale,
        fill=(0, 0, 0, 140),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(34 * scale))
    image.alpha_composite(shadow)
    shadow.close()

    draw = ImageDraw.Draw(image)
    card = (outer_x, outer_y, outer_x + card_width, outer_y + card_height)
    radius = 5 * scale
    draw.rounded_rectangle(card, radius=radius, fill=colors["surface"])

    for index, color in enumerate(("#FF5F56", "#FFBD2E", "#27C93F")):
        x = card[0] + (18 + index * 20) * scale
        y = card[1] + 14 * scale
        diameter = 12 * scale
        outlines = ("#E0443E", "#DEA123", "#1AAB29")
        draw.ellipse(
            (x, y, x + diameter, y + diameter),
            fill=color,
            outline=outlines[index],
            width=scale,
        )

    y = card[1] + padding_top
    for line in lines:
        _draw_highlighted_line(
            draw,
            line,
            card[0] + padding_left,
            y,
            fonts,
            colors,
            language,
        )
        y += line_height

    if bg_color is None:
        image.save(output_path, "PNG")
    else:
        rgb_image = image.convert("RGB")
        rgb_image.save(output_path, "PNG", optimize=True)
        rgb_image.close()
    image.close()
    return output_path


def _normalize_code(code: str) -> str:
    stripped = code.strip("\n")
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped.rstrip("\n")


def _resolve_background(background: str) -> str | None:
    if background in BACKGROUNDS:
        return BACKGROUNDS[background]
    if re.fullmatch(r"#?[0-9A-Fa-f]{6}", background):
        return background if background.startswith("#") else f"#{background}"
    return BACKGROUNDS["carbon"]


def _wrap_lines(lines: list[str], fonts: CodeFontBundle, max_width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if _text_length(line, fonts) <= max_width:
            wrapped.append(line)
            continue
        current = ""
        indent = " " * (len(line) - len(line.lstrip(" ")))
        for part in re.split(r"(\s+)", line):
            candidate = f"{current}{part}"
            if current and _text_length(candidate, fonts) > max_width:
                wrapped.append(current.rstrip())
                current = f"{indent}    {part.lstrip()}"
            else:
                current = candidate
        if current:
            wrapped.append(current.rstrip())
    return wrapped


def _draw_highlighted_line(
    draw: ImageDraw.ImageDraw,
    line: str,
    x: int,
    y: int,
    fonts: CodeFontBundle,
    colors: dict[str, str],
    language: str,
) -> None:
    if language == "text":
        _draw_text(draw, line, x, y, fonts, colors["text"])
        return

    if _draw_pygments_line(draw, line, x, y, fonts, colors, language):
        return

    token_pattern = _token_pattern(language)
    cursor = x
    last_end = 0
    for match in token_pattern.finditer(line):
        if match.start() > last_end:
            plain = line[last_end : match.start()]
            cursor = _draw_text(draw, plain, cursor, y, fonts, colors["text"])

        token = match.group(0)
        fill = _token_color(token, colors, language)
        cursor = _draw_text(draw, token, cursor, y, fonts, fill)
        last_end = match.end()

    if last_end < len(line):
        tail = line[last_end:]
        _draw_text(draw, tail, cursor, y, fonts, colors["text"])


def _token_color(token: str, colors: dict[str, str], language: str) -> str:
    keyword_sets = {
        "javascript": {"const", "let", "var", "function", "return", "if", "else", "for", "while", "class", "import", "from", "async", "await"},
        "typescript": {"const", "let", "var", "function", "return", "if", "else", "for", "while", "class", "import", "from", "type", "interface", "async", "await"},
        "java": {"class", "public", "private", "protected", "static", "void", "return", "new", "if", "else", "for", "while", "import"},
        "csharp": {"class", "public", "private", "protected", "static", "void", "return", "new", "if", "else", "for", "while", "using", "namespace"},
        "cpp": {"class", "public", "private", "protected", "return", "new", "if", "else", "for", "while", "include", "using", "namespace", "auto"},
        "go": {"func", "package", "import", "return", "if", "else", "for", "range", "type", "struct", "interface", "go", "defer"},
        "php": {"function", "class", "public", "private", "protected", "return", "if", "else", "foreach", "while", "namespace", "use"},
        "ruby": {"def", "class", "module", "end", "return", "if", "else", "elsif", "do", "require"},
        "sql": {"select", "from", "where", "join", "inner", "left", "right", "insert", "update", "delete", "create", "table", "group", "order", "by"},
        "bash": {"if", "then", "else", "fi", "for", "in", "do", "done", "case", "esac", "function", "export"},
        "html": {"html", "head", "body", "div", "span", "section", "script", "style", "class", "id"},
        "css": {"display", "grid", "flex", "color", "background", "font", "margin", "padding", "border"},
        "json": {"true", "false", "null"},
    }
    if token.startswith(("#", "//", "/*")):
        return colors["comment"]
    if token.startswith(("\"", "'", "`")):
        return colors["string"]
    if language == "html" and re.fullmatch(r"</?[A-Za-z][A-Za-z0-9-]*|/?>", token):
        return colors["keyword"]
    if language == "css" and token.startswith((".", "#")):
        return colors["keyword"]
    if token.startswith("--"):
        return colors["operator"]
    if token.replace(".", "", 1).isdigit():
        return colors["number"]
    if re.fullmatch(r"=>|==|!=|<=|>=|::|->|[+\-*/%=<>|&:;,{}()[\].]+", token):
        return colors["operator"]
    if language == "python" and keyword.iskeyword(token):
        return colors["keyword"]
    if token.lower() in keyword_sets.get(language, set()):
        return colors["keyword"]
    return colors["text"]


def _draw_pygments_line(
    draw: ImageDraw.ImageDraw,
    line: str,
    x: int,
    y: int,
    fonts: CodeFontBundle,
    colors: dict[str, str],
    language: str,
) -> bool:
    lexer_name = _lexer_name(language)
    if lexer_name is None:
        return False
    try:
        lexer = get_lexer_by_name(lexer_name, stripnl=False)
    except ClassNotFound:
        return False

    cursor = x
    try:
        tokens = lex(line, lexer)
    except Exception:
        return False
    for token_type, value in tokens:
        if not value:
            continue
        value = value.replace("\n", "")
        if not value:
            continue
        fill = _pygments_color(token_type, colors)
        cursor = _draw_text(draw, value, cursor, y, fonts, fill)
    return True


def _lexer_name(language: str) -> str | None:
    return {
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
        "java": "java",
        "csharp": "csharp",
        "cpp": "cpp",
        "go": "go",
        "php": "php",
        "ruby": "ruby",
        "sql": "sql",
        "html": "html",
        "css": "css",
        "json": "json",
        "bash": "bash",
    }.get(language)


def _pygments_color(token_type: Token, colors: dict[str, str]) -> str:
    if token_type in Comment:
        return colors["comment"]
    if token_type in Keyword:
        return colors["keyword"]
    if token_type in String:
        return colors["string"]
    if token_type in Number:
        return colors["number"]
    if token_type in Operator:
        return colors["operator"]
    if token_type in Punctuation:
        return colors["punctuation"]
    if token_type in Name.Function or token_type in Name.Class or token_type in Name.Decorator:
        return colors["name"]
    if token_type in Literal:
        return colors["number"]
    return colors["text"]


def _token_pattern(language: str) -> re.Pattern[str]:
    if language == "html":
        return re.compile(r"(<!--.*?-->|</?[A-Za-z][A-Za-z0-9-]*|/?>|\".*?\"|'.*?'|=|\b[A-Za-z_:][-A-Za-z0-9_:.]*\b)", re.DOTALL)
    if language == "css":
        return re.compile(r"(/\*.*?\*/|#[0-9A-Fa-f]{3,8}|[.#]?[A-Za-z_-][A-Za-z0-9_-]*|\".*?\"|'.*?'|\b\d+(?:\.\d+)?(?:px|rem|em|%|vh|vw)?\b|[{}:;,()>+~*=])", re.DOTALL)
    if language == "json":
        return re.compile(r"(\"(?:\\.|[^\"])*\"|\btrue\b|\bfalse\b|\bnull\b|-?\b\d+(?:\.\d+)?\b|[{}[\]:,])")
    if language == "python":
        return re.compile(r"(#.*$|\"\"\".*?\"\"\"|'''.*?'''|\".*?\"|'.*?'|==|!=|<=|>=|:=|->|[+\-*/%=<>|&:;,{}()[\].]+|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b)", re.DOTALL)
    if language in {"javascript", "typescript"}:
        return re.compile(r"(//.*$|/\*.*?\*/|\".*?\"|'.*?'|`.*?`|=>|===|!==|==|!=|<=|>=|[+\-*/%=<>|&:;,{}()[\].]+|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][A-Za-z0-9_$]*\b)", re.DOTALL)
    return re.compile(r"(#.*$|//.*$|\".*?\"|'.*?'|`.*?`|=>|==|!=|<=|>=|::|->|[+\-*/%=<>|&:;,{}()[\].]+|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][A-Za-z0-9_$]*\b)")


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        str(BASE_DIR / "bot" / "assets" / "fonts" / "Hack-Regular.ttf"),
        "C:/Windows/Fonts/CascadiaMono.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/lucon.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _emoji_font(size: int) -> ImageFont.FreeTypeFont | None:
    for path in (
        "C:/Windows/Fonts/seguiemj.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return None


def _font_bundle(size: int) -> CodeFontBundle:
    primary = _font(size)
    emoji = _emoji_font(size)
    return CodeFontBundle(
        primary=primary,
        emoji=emoji,
        primary_codepoints=_font_codepoints(getattr(primary, "path", None)),
        emoji_codepoints=_font_codepoints(getattr(emoji, "path", None)),
    )


@lru_cache(maxsize=16)
def _font_codepoints(path: str | bytes | None) -> frozenset[int]:
    if not path:
        return frozenset()
    try:
        font = TTFont(path, lazy=True, fontNumber=0)
        try:
            return frozenset(
                codepoint
                for table in font["cmap"].tables
                for codepoint in table.cmap
            )
        finally:
            font.close()
    except (OSError, KeyError):
        return frozenset()


def _text_length(text: str, fonts: CodeFontBundle) -> int:
    return sum(_run_length(value, font) for value, font, _ in _font_runs(text, fonts))


def _draw_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    fonts: CodeFontBundle,
    fill: str,
) -> int:
    cursor = x
    for value, font, embedded_color in _font_runs(text, fonts):
        if embedded_color:
            try:
                draw.text((cursor, y), value, font=font, fill=fill, embedded_color=True)
            except ValueError:
                draw.text((cursor, y), value, font=font, fill=fill)
        else:
            draw.text((cursor, y), value, font=font, fill=fill)
        cursor += _run_length(value, font)
    return cursor


def _font_runs(
    text: str,
    fonts: CodeFontBundle,
) -> list[tuple[str, ImageFont.ImageFont, bool]]:
    runs: list[tuple[str, ImageFont.ImageFont, bool]] = []
    for cluster in _grapheme_clusters(text):
        base_codepoints = [
            codepoint
            for codepoint in map(ord, cluster)
            if codepoint not in {0x200D, 0xFE0E, 0xFE0F}
        ]
        emoji_supports_cluster = any(
            codepoint in fonts.emoji_codepoints for codepoint in base_codepoints
        )
        explicitly_emoji = "\ufe0f" in cluster
        missing_from_primary = any(
            codepoint not in fonts.primary_codepoints for codepoint in base_codepoints
        )
        use_emoji = (
            fonts.emoji is not None
            and emoji_supports_cluster
            and (explicitly_emoji or missing_from_primary)
        )
        font = fonts.emoji if use_emoji and fonts.emoji is not None else fonts.primary
        value = cluster.replace("\ufe0e", "").replace("\ufe0f", "") if use_emoji else cluster
        if runs and runs[-1][1] is font and runs[-1][2] == use_emoji:
            previous, _, _ = runs[-1]
            runs[-1] = (previous + value, font, use_emoji)
        else:
            runs.append((value, font, use_emoji))
    return runs


def _grapheme_clusters(text: str) -> list[str]:
    clusters: list[str] = []
    current = ""
    regional_count = 0
    for character in text:
        codepoint = ord(character)
        is_regional = 0x1F1E6 <= codepoint <= 0x1F1FF
        joins_previous = bool(current) and (
            current.endswith("\u200d")
            or character == "\u200d"
            or codepoint in {0xFE0E, 0xFE0F, 0x20E3}
            or 0x1F3FB <= codepoint <= 0x1F3FF
            or bool(unicodedata.combining(character))
            or (is_regional and regional_count % 2 == 1)
        )
        if current and not joins_previous:
            clusters.append(current)
            current = ""
            regional_count = 0
        current += character
        regional_count = regional_count + 1 if is_regional else 0
    if current:
        clusters.append(current)
    return clusters


def _run_length(text: str, font: ImageFont.ImageFont) -> int:
    if hasattr(font, "getlength"):
        return max(0, round(font.getlength(text)))
    return len(text) * 10
