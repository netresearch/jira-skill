#!/bin/bash

# Jira Wiki Markup Syntax Validator
# Checks text for common Jira syntax errors and suggests corrections

set -e

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Counters
ERRORS=0
WARNINGS=0

# Function to print error
# Use pre-increment so the (( )) expression is the new (non-zero) value;
# `((ERRORS++))` returns the OLD value (0 on first call) and trips `set -e`.
error() {
    echo -e "${RED}❌ ERROR:${NC} $1"
    ((++ERRORS))
}

# Function to print warning
warning() {
    echo -e "${YELLOW}⚠️  WARNING:${NC} $1"
    ((++WARNINGS))
}

# Function to print success
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Function to check file
validate_file() {
    local file="$1"
    echo ""
    echo "=========================================="
    echo "Validating: $file"
    echo "=========================================="

    if [ ! -f "$file" ]; then
        error "File not found: $file"
        return
    fi

    # Hybrid template files (templates/*.md) are a Markdown wrapper carrying
    # the Jira markup inside ``` fences. For those, validate the fenced
    # payload: untagged ``` fences hold Jira markup to be copy-pasted;
    # language-tagged fences (```bash) are foreign code and are skipped, as is
    # the wrapper prose. Files without fences — drafts about to be posted —
    # keep the full strict treatment.
    local content
    if grep -qE '^[[:space:]]*```' "$file"; then
        echo "   (hybrid file: validating untagged \`\`\` fenced payload as Jira markup)"
        content=$(awk '
            /^[[:space:]]*```/ {
                if (infence) { infence = 0 }
                else { infence = 1; tagged = ($0 ~ /^[[:space:]]*```./) }
                next
            }
            infence && !tagged { print }
        ' "$file")
    else
        content=$(cat "$file")
    fi

    # Check for Markdown-style headings (## instead of h2.)
    if echo "$content" | grep -qE "^##+ "; then
        error "Found Markdown-style headings (##). Use Jira format: h2. Heading"
        echo "   Lines with issue:"
        echo "$content" | grep -nE "^##+ " | head -5
    fi

    # Check for Markdown-style bold (**text** instead of *text*)
    if echo "$content" | grep -qE "\*\*[^*]+\*\*"; then
        warning "Found Markdown-style bold (**text**). Use Jira format: *text*"
        echo "   Examples found:"
        echo "$content" | grep -oE "\*\*[^*]+\*\*" | head -3
    fi

    # Check for Markdown-style italic (_text_ is ok, but *text* for bold might be confused)
    if echo "$content" | grep -qE "\*[^*]+\*\*[^*]+\*"; then
        warning "Found potential Markdown-style italic mixed with bold"
    fi

    # Check for Markdown-style code blocks (``` instead of {code})
    if echo "$content" | grep -qE "^\`\`\`"; then
        error "Found Markdown code blocks (\`\`\`). Use Jira format: {code:language}"
        echo "   Lines with issue:"
        echo "$content" | grep -nE "^\`\`\`" | head -5
    fi

    # Check for Markdown-style inline code (` instead of {{)
    if grep -qE "\`[^\`]+\`" <<< "$content"; then
        warning "Found Markdown inline code (\`code\`). Consider Jira format: {{code}}"
    fi

    # Check for unescaped { or } inside {{...}} monospace blocks. The Jira parser
    # is greedy and breaks on raw inner braces, rendering the block as raw text
    # (e.g. {{compose.example.{yml,override.pga.yml}}} renders verbatim).
    # Backslash-escaped braces (\{ \}) render literally and are fine.
    # Two failure modes:
    #   1. {{ followed by another raw { before any } — e.g. {{path/{a,b}.txt}}
    #      or {{a{b}c}}.
    #   2. A {{ block with an extra raw } before the closing }} — e.g. {{a}b}}.
    # `([^...\\]|\\.)*` skips escaped characters so \{ and \} don't false-positive.
    local brace_re='\{\{([^{}\\]|\\.)*\{|\{\{([^{}\\]|\\.)*\}([^{}\\]|\\.)*\}\}'
    if grep -qE "$brace_re" <<< "$content"; then
        error "Found unescaped { or } inside {{...}} monospace block — Jira parser will render it as raw text. Escape as \\{ \\} or split the reference."
        echo "   Lines with issue:"
        grep -nE "$brace_re" <<< "$content" | head -3
    fi

    # Check for unescaped * inside {{...}} monospace blocks. Jira still parses
    # inline markup inside {{...}}: a * pair turns bold mid-token
    # (e.g. {{jira-*backup-*}} renders "backup-" bold). Escape as \*.
    local star_re='\{\{([^{}*\\]|\\.)*\*'
    if grep -qE "$star_re" <<< "$content"; then
        warning "Found unescaped * inside {{...}} monospace block — renders as bold mid-token. Escape as \\* (e.g. {{jira-\\*backup-\\*}})."
        echo "   Lines with issue:"
        grep -nE "$star_re" <<< "$content" | head -3
    fi

    # Check for dash pairs Jira renders as a strikethrough span (`-text-`).
    #
    # This is the same grammar as find_strikethrough_spans() in
    # skills/jira-communication/scripts/lib/markup.py, and both are measured
    # against a live Jira Server 9.12 renderer rather than reasoned about:
    # tests/test_validator_parity.py runs BOTH implementations over the
    # single-line cases in tests/fixtures/strikethrough_oracle.json and asserts
    # they agree. It does NOT cover multi-line input, tables or headings, so
    # block handling is pinned separately in tests/test_strikethrough.py, which
    # also holds the Python side against the recorded corpus.
    #
    #   opener  an unescaped `-` at line start or after a non-word character
    #           (which includes the `}}`, `*`, `_`, `]`, `!` that end an inline
    #           element — that is why {{mono}}-Extensions opens a span), and
    #           followed by neither whitespace nor another dash
    #   closer  the first LATER unescaped `-` that is not preceded by
    #           whitespace and is followed by a non-word character or end of
    #           line; dashes that fail those conditions are skipped over. A
    #           dash that leads a word can never close, which is why
    #           `journalctl -b -p crit` alone is not a span — but the same
    #           flags followed by `zu-` later on the line ARE one.
    #
    # Dashes inside {code}/{noformat} render literally, so those lines are
    # skipped via open/close toggling ({quote}/{panel} are NOT skipped — Jira
    # parses text effects inside them). Markdown ``` fences are skipped the
    # same way: their own check above already errors on them.
    #
    # Links, bare URLs and !images! are resolved into a single element before
    # text effects run, so a dash inside them is inert — the `/-/` in a GitLab
    # merge-request URL must not be escaped, or the link breaks. They are
    # masked out before the scan. {{monospace}} is NOT masked: text effects do
    # apply inside it.
    #
    # Word class: NOT space and NOT punct, which is locale-independent. Two
    # dead ends, both measured with gawk 5.2.1: [[:alnum:]] is locale-dependent
    # (ASCII-only under LC_ALL=C), and an explicit high-byte range
    # [\200-\377] is rejected outright in a multibyte locale ("Invalid
    # collation character"), killing the rule silently. Negating space and
    # punct agrees in both for ASCII and for non-ASCII LETTERS: a high byte is
    # neither space nor punct under C, and is alnum under UTF-8. It also
    # matches Jira, where `_` is NOT a word character.
    #
    # The one place the two locales genuinely disagree is non-ASCII
    # PUNCTUATION: under LC_ALL=C a typographic quote is a run of high bytes
    # and therefore reads as a word character, so `Der Wert "-x- ist falsch`
    # (German quotes) would be missed. tests/test_validator_parity.py caught
    # exactly that on five corpus cases. They are folded down to an ASCII
    # quote first, which behaves identically in both locales - gsub on a
    # literal UTF-8 string matches bytes under C and characters under UTF-8.
    # Run the scan under a UTF-8 locale when the machine has one. The word class
    # below is locale-independent for ASCII and for non-ASCII LETTERS, but not
    # for arbitrary non-ASCII PUNCTUATION: under LC_ALL=C a `§`, `€`, `°` or `±`
    # is a run of high bytes and reads as a word character, so the opener
    # boundary is lost and a real span is missed. fold() handles the handful of
    # codepoints that show up in prose; the locale handles the rest. On a
    # C-only machine the fold is what is left, and the gap is the unfolded
    # symbols - tests/test_validator_parity.py runs both locales to keep that
    # visible rather than silent.
    # JIRA_SYNTAX_SCAN_LOCALE overrides the choice, so the C-only fallback can
    # be exercised on a machine that does have UTF-8 (the parity test does that).
    local scan_locale="${JIRA_SYNTAX_SCAN_LOCALE:-}"
    if [ -z "$scan_locale" ]; then
        scan_locale=$(locale -a 2>/dev/null | grep -iE '\.(utf-?8)$' | head -1)
    fi
    : "${scan_locale:=C}"

    local dash_hits
    # AWK-DASH-SCAN-BEGIN (marker: tests/test_validator_parity.py extracts the
    # program between these two markers and runs it over the whole corpus in
    # one pass. Keep them.)
    dash_hits=$(LC_ALL="$scan_locale" awk '
        function fold(line) {
            # NBSP becomes \002, a sentinel that is neither space nor word.
            # It has to be BOTH at once, because Jira treats U+00A0 as two
            # different things: an ordinary character for the dash delimiters
            # (`a -x<NBSP>- y` IS struck through, measured) and a terminator
            # for the URL autolinker (`https://h/a<NBSP>/-/b` links only
            # `https://h/a`). Python gets this from `\s` matching U+00A0 while
            # _is_delimiter_space does not; here \002 is excluded from the
            # region classes below and from isword(). Folding it to a space
            # instead would break the delimiters, and folding it to punctuation
            # - which this did - let a region swallow the dashes after it.
            gsub(/\xc2\xa0/, "\002", line)
            gsub(/\xe2\x80\x9e|\xe2\x80\x9c|\xe2\x80\x9d|\xe2\x80\x98|\xe2\x80\x99|\xe2\x80\x9a/, "\"", line)
            gsub(/\xc2\xab|\xc2\xbb|\xe2\x80\xb9|\xe2\x80\xba/, "\"", line)
            gsub(/\xe2\x80\x93|\xe2\x80\x94|\xe2\x80\x90|\xe2\x80\xa6|\xe2\x80\xa2/, "\"", line)
            # Common non-ASCII symbols. Not exhaustive and cannot be - this is
            # the C-locale fallback only; where a UTF-8 locale exists the
            # scan runs under it and gawk classifies these itself.
            gsub(/\xc2\xa7|\xe2\x82\xac|\xc2\xb0|\xc2\xb1|\xc2\xb5|\xc3\x97|\xc3\xb7/, "\"", line)
            gsub(/\xc2\xa9|\xc2\xae|\xe2\x84\xa2|\xe2\x80\xa0|\xe2\x80\xa1|\xe2\x80\xb0/, "\"", line)
            return line
        }
        # The \001 test comes first: a masked region must read as a boundary, and a
        # control character is neither space nor punct, so it would otherwise
        # count as a word character and swallow the opener after a link.
        function isword(c) { return (c != "" && c != "\001" && c != "\002" && c !~ /[[:space:][:punct:]]/) }
        # Replace protected regions with \001, preserving length. Mirrors
        # _mask_protected() in lib/markup.py: a bare URL, mailto or image needs
        # an ASCII non-alphanumeric before it (one glued to a word is not
        # autolinked, so it keeps its dashes live) while a square-bracketed
        # link resolves anywhere, and a region starting exactly where the
        # previous one ended does not resolve either.
        function mask(line,    out, pos, rest, start, len_, before, kind, i, prev_end) {
            out = ""
            pos = 1
            prev_end = 0
            while (pos <= length(line)) {
                rest = substr(line, pos)
                if (!match(rest, /(\[[^]\n]*\])|((https?|ftp):\/\/[^][:space:]{}|\002]+)|(mailto:[^][:space:]{}|\002]+)|(![^[:space:]!\002]+!)/)) {
                    out = out rest
                    break
                }
                start = pos + RSTART - 1
                len_ = RLENGTH
                before = (start > 1) ? substr(line, start - 1, 1) : ""
                kind = substr(line, start, 1)

                # A backslash-escaped bracket or bang is not a macro, so its
                # content is ordinary prose and its dashes stay live. Same for a
                # region that does not sit at a boundary: a bare URL, mailto or
                # image needs a non-alphanumeric before it (and a URL must not
                # follow a pipe), while a square-bracketed link resolves
                # anywhere. In both cases the region is not a region, so the
                # scan resumes one character in - which is what the Python
                # regex does by simply not matching there.
                if (before == "\\" || (kind != "[" && (before ~ /[A-Za-z0-9]/ || (kind != "!" && (before == "|" || before == "!"))))) {
                    out = out substr(line, pos, RSTART)
                    pos = start + 1
                    continue
                }

                # Two regions written back to back do not both resolve: Jira
                # renders the first and leaves the second literal. The SECOND
                # one is skipped whole, not one character at a time - resuming
                # inside it would let a shorter region nested within it be
                # masked, which loses the dashes around it. That was a real
                # miss: `!i.png!https://h/a/-/b[t|...]` comes back struck and
                # the scan reported nothing. prev_end deliberately does not
                # advance here, so a third region is masked again, matching
                # _mask_protected() in lib/markup.py.
                if (start == prev_end) {
                    out = out substr(line, pos, RSTART - 1 + len_)
                    pos = start + len_
                    continue
                }

                out = out substr(line, pos, RSTART - 1)
                for (i = 0; i < len_; i++) out = out "\001"
                pos = start + len_
                prev_end = pos
            }
            return out
        }
        function strikes(raw,    line, n, i, j, prev, nxt, after) {
            line = mask(raw)
            n = length(line)
            for (i = 1; i <= n; i++) {
                if (substr(line, i, 1) != "-") continue
                if (i > 1 && substr(line, i - 1, 1) == "\\") continue
                prev = (i > 1) ? substr(line, i - 1, 1) : ""
                if (isword(prev)) continue
                nxt = (i < n) ? substr(line, i + 1, 1) : ""
                if (nxt == "" || nxt ~ /[[:space:]]/ || nxt == "-") continue
                for (j = i + 2; j <= n; j++) {
                    if (substr(line, j, 1) != "-") continue
                    if (substr(line, j - 1, 1) == "\\") continue
                    if (substr(line, j - 1, 1) ~ /[[:space:]]/) continue
                    after = (j < n) ? substr(line, j + 1, 1) : ""
                    if (isword(after)) continue
                    return 1
                }
            }
            return 0
        }
        # Only the SAME tag closes a block, exactly as the Jira renderer does
        # and as _split_verbatim() in lib/markup.py does. Toggling on either tag
        # loses track after `{noformat}` / `{code}` / `{noformat}`, and then
        # misses every span in the rest of the file.
        /^[[:space:]]*\{(code|noformat)(:[^}]*)?\}[[:space:]]*$/ {
            tag = $0
            sub(/^[[:space:]]*\{/, "", tag)
            sub(/[:}].*$/, "", tag)
            if (opentag == "") opentag = tag
            else if (opentag == tag) opentag = ""
            next
        }
        /^[[:space:]]*```/ { infence = !infence; next }
        opentag != "" || infence { next }
        strikes(fold($0)) { printf "%d:%s\n", NR, $0 }' <<< "$content")
    local dash_rc=$?
    # awk's status must not be swallowed by the pipe: a scan that never ran
    # (no awk, a syntax error, a killed process) produces no hits, and no hits
    # is what a clean draft looks like. That is the same "a failure reads as
    # clean" shape RenderVerdict.available exists to prevent on the Python
    # side, and it is an ERROR here rather than silence.
    if [ "$dash_rc" -ne 0 ]; then
        error "The dash-strikethrough scan did not run (awk exited $dash_rc) - this draft was NOT checked for spans Jira would render struck through."
        dash_hits=""
    else
        dash_hits=$(printf '%s\n' "$dash_hits" | grep -v '^$' | head -3)
    fi
    # AWK-DASH-SCAN-END
    if [ -n "$dash_hits" ]; then
        warning "Found a dash pair that renders struck through outside a code block — Jira reads a dash after a non-word character (including the {{}}, *, _, ] or ! that ends an inline element) as a strikethrough opener, and a dash before one as the closer. Escape the opener as \\-foo; a backslash-escaped dash still prints as a plain hyphen."
        echo "   Lines with issue:"
        echo "$dash_hits"
    fi

    # Check for Markdown-style links ([text](url) instead of [text|url])
    if echo "$content" | grep -qE "\[([^\]]+)\]\(([^)]+)\)"; then
        error "Found Markdown-style links ([text](url)). Use Jira format: [text|url]"
        echo "   Examples found:"
        echo "$content" | grep -oE "\[([^\]]+)\]\(([^)]+)\)" | head -3
    fi

    # Check for headings without space after period (h2.Title instead of h2. Title)
    if echo "$content" | grep -qE "^h[1-6]\.[^ ]"; then
        error "Found headings without space after period. Use: h2. Title (not h2.Title)"
        echo "   Lines with issue:"
        echo "$content" | grep -nE "^h[1-6]\.[^ ]" | head -5
    fi

    # Check for code blocks without language specification
    # (skip escaped \{code\} literals and inline-monospace {{code}})
    if grep -qE '(^|[^\\{])\{code\}[^{]' <<< "$content"; then
        warning "Found {code} blocks without language. Consider: {code:java} for syntax highlighting"
    fi

    # Check for {code:LANG} using a language Jira Server's formatter does not recognize.
    # Authoritative list from the server error message ("Available languages are: ...").
    # Anything outside this set causes "Unable to find source-code formatter for language: X".
    # Use Bash built-in pattern matching with literal-quoted needle so identifiers
    # containing shell-significant characters (c#, c++) are compared verbatim.
    local valid_langs="actionscript ada applescript bash c c# c++ cpp css erlang go groovy haskell html java javascript js json lua none nyan objc perl php python r rainbow ruby scala sh sql swift visualbasic xml yaml"
    local search_langs=" $valid_langs "
    while IFS= read -r lang; do
        [ -z "$lang" ] && continue
        # Templates ship `{code:language}` as a fill-in placeholder; warn rather than
        # error so templates stay validatable until users substitute a real lang.
        if [ "$lang" = "language" ]; then
            warning "Found {code:language} placeholder — replace with an actual language before submitting to Jira"
            continue
        fi
        if [[ "$search_langs" != *" $lang "* ]]; then
            # Suggest the closest-fit valid language for common stumbles before
            # falling back to the generic "use {code:none} or ..." message.
            # Lower-case the identifier so `Dockerfile`, `Makefile` etc. match
            # without per-variant case entries.
            local hint=""
            case "${lang,,}" in
                hcl|tf|terraform|tofu)               hint="{code:none} for HCL / Terraform / OpenTofu" ;;
                dockerfile|containerfile)            hint="{code:bash} (Dockerfile RUN lines lex acceptably as bash) or {code:none}" ;;
                rust|rs)                             hint="{code:none} for Rust" ;;
                kotlin|kt)                           hint="{code:java} (Kotlin lexes acceptably as Java) or {code:none}" ;;
                typescript|ts|tsx)                   hint="{code:javascript} or {code:none}" ;;
                shell|zsh|fish|console)              hint="{code:bash} or {code:none}" ;;
                powershell|ps1|pwsh)                 hint="{code:none} for PowerShell" ;;
                make|makefile)                       hint="{code:none} for Makefile" ;;
                ini|toml|conf|properties)            hint="{code:none} for INI / TOML / config" ;;
                diff|patch)                          hint="{code:none}" ;;
                go-template|gotmpl|jinja|jinja2)     hint="{code:none}" ;;
            esac
            if [ -n "$hint" ]; then
                error "Unsupported {code:$lang} language. Jira Server rejects this; use $hint"
            else
                error "Unsupported {code:$lang} language. Jira Server rejects this; use {code:none} or one of: $valid_langs"
            fi
        fi
    done < <(grep -oE '(^|[^\\{])\{code:[^}|\\]+' <<< "$content" | sed 's/.*{code://' | sort -u)

    # Check for tables with incorrect header syntax (|Header| instead of ||Header||)
    if echo "$content" | grep -qE "^\|[^|]+\|$" && ! echo "$content" | grep -qE "^\|\|"; then
        warning "Potential table header without double pipes. Headers should use: ||Header||"
    fi

    # Check for unclosed {code} blocks
    # Jira wiki markup uses {code} as both the opening and closing tag, so a
    # correctly paired block always produces an even occurrence count.
    # Use `grep -o ... | wc -l` to count each occurrence (not just matching
    # lines), matching the {color} check below for consistency and to catch
    # multiple tags on the same line.
    # `(^|[^\\{])` skips escaped literals (\{code\}) and inline-monospace
    # lookalikes ({{code}}) — both are prose, not block markup.
    local code_count
    code_count=$(grep -oE '(^|[^\\{])\{code[}:]' <<< "$content" | wc -l)
    if [ $((code_count % 2)) -ne 0 ]; then
        error "Mismatched {code} tags: odd number ($code_count) of occurrences (expected pairs)"
    fi

    # Check for unclosed {panel} blocks
    # Same rule applies: {panel} opens and closes the block.
    local panel_count
    panel_count=$(grep -oE '(^|[^\\{])\{panel[}:]' <<< "$content" | wc -l)
    if [ $((panel_count % 2)) -ne 0 ]; then
        error "Mismatched {panel} tags: odd number ($panel_count) of occurrences (expected pairs)"
    fi

    # Check for unclosed {color} blocks
    local color_count
    color_count=$(echo "$content" | grep -o "{color" | wc -l)
    if [ $((color_count % 2)) -ne 0 ]; then
        warning "Potential unclosed {color} tag (odd number of occurrences)"
    fi

    # Check for unclosed {noformat}, {quote}, {anchor} blocks
    # Same single-token open/close rule as {code}, {panel}, {color}: an odd
    # occurrence count signals an unescaped literal in prose or a missing close.
    for macro in noformat quote anchor; do
        local mcount
        mcount=$(grep -oE "(^|[^\\\\{])\{${macro}[}:]" <<< "$content" | wc -l)
        if [ $((mcount % 2)) -ne 0 ]; then
            warning "Potential unclosed {${macro}} tag (odd number of occurrences)"
        fi
    done

    # Check for block-markup tags used inline. {code}, {noformat}, {quote} and
    # {panel} are block-level macros: the tag must stand alone on its own line.
    # An unescaped tag with other text on the same line opens the block
    # mid-prose and swallows the rest of the line (classic case: writing
    # *about* {code} in a sentence). Escape literal mentions as \{code\}.
    # Escaped tags (\{code\}) and {{monospace}} lookalikes ({{code}}) are
    # stripped per line BEFORE testing — a line-level exclusion would hide a
    # genuine unescaped tag sharing a line with an escaped/monospace mention.
    local inline_hits
    inline_hits=$(awk '
        {
            line = $0
            gsub(/\\\{(code|noformat|quote|panel)[^}]*\\\}/, "", line)
            gsub(/\{\{(code|noformat|quote|panel)(:[^}]*)?\}\}/, "", line)
            if (line ~ /\{(code|noformat|quote|panel)(:[^}]*)?\}/ &&
                line !~ /^[[:space:]]*\{(code|noformat|quote|panel)(:[^}]*)?\}[[:space:]]*$/)
                printf "%d:%s\n", NR, $0
        }' <<< "$content" | head -3)
    if [ -n "$inline_hits" ]; then
        error "Block tag used inline — {code}/{noformat}/{quote}/{panel} must stand alone on their own line; escape literal mentions as \\{code\\}"
        echo "   Lines with issue:"
        echo "$inline_hits"
    fi

    # Check for Markdown-style lists (- item instead of * item)
    if echo "$content" | grep -qE "^- [^-]"; then
        warning "Found Markdown-style bullets (- item). Jira prefers: * item"
    fi

    # Positive checks
    if echo "$content" | grep -qE "^h[1-6]\. "; then
        success "Found correctly formatted Jira headings"
    fi

    if echo "$content" | grep -qE "{code:[a-z]+}"; then
        success "Found code blocks with language specification"
    fi

    if echo "$content" | grep -qE "\[~[a-z.]+\]"; then
        success "Found user mentions ([~username])"
    fi

    if echo "$content" | grep -qE "\[[A-Z]+-[0-9]+\]"; then
        success "Found issue links ([PROJ-123])"
    fi
}

# Main script
echo "Jira Wiki Markup Syntax Validator"
echo "=================================="

if [ $# -eq 0 ]; then
    echo "Usage: $0 <file1> [file2] [file3] ..."
    echo ""
    echo "Validates Jira wiki markup syntax in text files"
    echo ""
    echo "Example:"
    echo "  $0 issue-description.txt"
    echo "  $0 templates/*.md"
    exit 1
fi

# Validate each file
for file in "$@"; do
    validate_file "$file"
done

# Summary
echo ""
echo "=========================================="
echo "Validation Summary"
echo "=========================================="
echo "Files checked: $#"
echo -e "${RED}Errors: $ERRORS${NC}"
echo -e "${YELLOW}Warnings: $WARNINGS${NC}"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed!${NC}"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  No errors, but $WARNINGS warnings found${NC}"
    exit 0
else
    echo -e "${RED}❌ $ERRORS errors found - please fix before submitting to Jira${NC}"
    exit 1
fi
