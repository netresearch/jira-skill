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

    local content=$(cat "$file")
    local line_num=0

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

    # Check for literal { or } inside {{...}} monospace blocks. The Jira parser
    # is greedy and breaks on inner braces, rendering the block as raw text
    # (e.g. {{compose.example.{yml,override.pga.yml}}} renders verbatim).
    # Two failure modes:
    #   1. {{ followed by another { before any } — e.g. {{path/{a,b}.txt}}
    #      or {{a{b}c}}.
    #   2. A {{ block with an extra } before the closing }} — e.g. {{a}b}}.
    # ERE alternation: the first branch catches mode 1 robustly without needing
    # to span the closing }}; the second branch catches mode 2.
    if grep -qE '\{\{[^}]*\{|\{\{[^{]*\}[^{]*\}\}' <<< "$content"; then
        error "Found literal { or } inside {{...}} monospace block — Jira parser will render it as raw text. Split the reference or escape the braces."
        echo "   Lines with issue:"
        grep -nE '\{\{[^}]*\{|\{\{[^{]*\}[^{]*\}\}' <<< "$content" | head -3
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
    if echo "$content" | grep -qE "{code}[^{]"; then
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
    done < <(grep -oE '\{code:[^}|]+' <<< "$content" | sed 's/^{code://' | sort -u)

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
    local code_count=$(grep -oE "\{code[}:]" <<< "$content" | wc -l)
    if [ $((code_count % 2)) -ne 0 ]; then
        error "Mismatched {code} tags: odd number ($code_count) of occurrences (expected pairs)"
    fi

    # Check for unclosed {panel} blocks
    # Same rule applies: {panel} opens and closes the block.
    local panel_count=$(grep -oE "\{panel[}:]" <<< "$content" | wc -l)
    if [ $((panel_count % 2)) -ne 0 ]; then
        error "Mismatched {panel} tags: odd number ($panel_count) of occurrences (expected pairs)"
    fi

    # Check for unclosed {color} blocks
    local color_count=$(echo "$content" | grep -o "{color" | wc -l)
    if [ $((color_count % 2)) -ne 0 ]; then
        warning "Potential unclosed {color} tag (odd number of occurrences)"
    fi

    # Check for unclosed {noformat}, {quote}, {anchor} blocks
    # Same single-token open/close rule as {code}, {panel}, {color}: an odd
    # occurrence count signals an unescaped literal in prose or a missing close.
    for macro in noformat quote anchor; do
        local mcount=$(grep -oE "\{${macro}[}:]" <<< "$content" | wc -l)
        if [ $((mcount % 2)) -ne 0 ]; then
            warning "Potential unclosed {${macro}} tag (odd number of occurrences)"
        fi
    done

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
