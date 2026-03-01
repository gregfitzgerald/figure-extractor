#!/usr/bin/env bash
# Figure Extractor CLI helper
# Usage: figure-extractor.sh <command> [args]

set -e

PROJECTS_DIR="/mnt/c/Users/gregs/Drive/figure-extraction-projects"
TOOL_PATH="/mnt/c/Users/gregs/Drive/tools/figure-extractor.html"
PDF_CONVERTER="/mnt/c/Users/gregs/Drive/tools/pdf-to-pages.py"

usage() {
    cat << EOF
Figure Extractor CLI

Usage: $(basename "$0") <command> [args]

Commands:
    convert <pdf> <name> [--dpi N]   Convert PDF to page images
    list                              List articles in projects folder
    open                              Open the figure extractor tool
    info <article>                    Show article info (page count, etc.)
    help                              Show this help

Examples:
    $(basename "$0") convert paper.pdf chen2011
    $(basename "$0") convert paper.pdf chen2011 --dpi 200
    $(basename "$0") list
    $(basename "$0") open
    $(basename "$0") info chen2011

Projects directory: $PROJECTS_DIR
EOF
}

cmd_convert() {
    local pdf="$1"
    local name="$2"
    shift 2
    
    if [[ -z "$pdf" || -z "$name" ]]; then
        echo "Error: convert requires <pdf> and <name>"
        echo "Usage: $(basename "$0") convert <pdf> <article_name> [--dpi N]"
        exit 1
    fi
    
    if [[ ! -f "$pdf" ]]; then
        echo "Error: PDF not found: $pdf"
        exit 1
    fi
    
    local output_dir="$PROJECTS_DIR/$name"
    
    echo "Converting: $pdf"
    echo "Output: $output_dir"
    
    python3 "$PDF_CONVERTER" "$pdf" "$output_dir" "$@"
}

cmd_list() {
    echo "Articles in $PROJECTS_DIR:"
    echo
    
    if [[ ! -d "$PROJECTS_DIR" ]]; then
        echo "  (projects directory not found)"
        exit 1
    fi
    
    local found=0
    for dir in "$PROJECTS_DIR"/*/; do
        if [[ -d "$dir" ]]; then
            local name=$(basename "$dir")
            local count=$(find "$dir" -maxdepth 1 -name "*.png" 2>/dev/null | wc -l)
            if [[ $count -gt 0 ]]; then
                printf "  %-30s %3d pages\n" "$name" "$count"
                found=1
            fi
        fi
    done
    
    if [[ $found -eq 0 ]]; then
        echo "  (no articles found)"
    fi
}

cmd_open() {
    echo "Opening Figure Extractor..."
    /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -Command \
        "Start-Process 'C:\\Users\\gregs\\Drive\\tools\\figure-extractor.html'"
}

cmd_info() {
    local name="$1"
    
    if [[ -z "$name" ]]; then
        echo "Error: info requires <article_name>"
        exit 1
    fi
    
    local dir="$PROJECTS_DIR/$name"
    
    if [[ ! -d "$dir" ]]; then
        echo "Error: Article not found: $name"
        exit 1
    fi
    
    local count=$(find "$dir" -maxdepth 1 -name "*.png" | wc -l)
    
    echo "Article: $name"
    echo "Path: $dir"
    echo "Pages: $count"
    
    if [[ -f "$dir/metadata.json" ]]; then
        echo
        echo "Metadata:"
        cat "$dir/metadata.json"
    fi
}

# Main
case "${1:-}" in
    convert)
        shift
        cmd_convert "$@"
        ;;
    list)
        cmd_list
        ;;
    open)
        cmd_open
        ;;
    info)
        shift
        cmd_info "$@"
        ;;
    help|--help|-h|"")
        usage
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run '$(basename "$0") help' for usage"
        exit 1
        ;;
esac
