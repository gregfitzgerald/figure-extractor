#!/usr/bin/env bash
# Figure Extractor CLI helper
# Usage: figure-extractor.sh <command> [args]

set -e

# Defaults resolve relative to this repo; override via environment variables.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

PROJECTS_DIR="${FIGURE_PROJECTS_DIR:-$HOME/figure-extraction-projects}"
TOOL_PATH="${FIGURE_TOOL_PATH:-$REPO_DIR/figure-extractor.html}"
PDF_CONVERTER="${FIGURE_PDF_CONVERTER:-$SCRIPT_DIR/pdf-to-pages.py}"
SCORER="${FIGURE_SCORER:-$SCRIPT_DIR/score.py}"

usage() {
    cat << EOF
Figure Extractor CLI

Usage: $(basename "$0") <command> [args]

Commands:
    convert <pdf> <name> [--dpi N]   Convert PDF to page images (+ text.json caption sidecar)
    list                              List articles in projects folder
    open                              Open the figure extractor tool
    info <article>                    Show article info (page count, etc.)

  Evaluation (score extraction against hand-corrected ground truth):
    promote <article>                 Copy an article's annotations.json to ground-truth.json
    datasets                          Show which articles have predicted / ground-truth
    score <article>                   Score one article vs its ground-truth.json
    score-all                         Score every article that has both; print aggregate
    gate [--min-f1 X]                 score-all + regression gate (nonzero exit on drop)

    help                              Show this help

Examples:
    $(basename "$0") convert paper.pdf chen2011
    $(basename "$0") promote chen2011      # after hand-correcting + exporting into the article dir
    $(basename "$0") score chen2011
    $(basename "$0") gate

Projects directory: $PROJECTS_DIR
EOF
}

cmd_promote() {
    local name="$1"
    if [[ -z "$name" ]]; then echo "Error: promote requires <article_name>"; exit 1; fi
    local dir="$PROJECTS_DIR/$name"
    local src="$dir/annotations.json"
    local dst="$dir/ground-truth.json"
    if [[ ! -f "$src" ]]; then echo "Error: no annotations.json in $dir (export a correction there first)"; exit 1; fi
    if [[ -f "$dst" ]]; then
        cp "$dst" "$dst.bak.$(date +%Y%m%d%H%M%S)"
        echo "Backed up existing ground-truth.json"
    fi
    cp "$src" "$dst"
    echo "Promoted $name/annotations.json -> ground-truth.json"
}

cmd_score() {
    python3 "$SCORER" --projects-dir "$PROJECTS_DIR" "$@"
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
    echo "Opening Figure Extractor: $TOOL_PATH"
    if command -v wslview >/dev/null 2>&1; then
        wslview "$TOOL_PATH"
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$TOOL_PATH"
    elif command -v open >/dev/null 2>&1; then
        open "$TOOL_PATH"
    else
        echo "No opener found -- open this file in your browser: $TOOL_PATH"
    fi
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
    promote)
        shift
        cmd_promote "$@"
        ;;
    datasets)
        cmd_score datasets
        ;;
    score)
        shift
        cmd_score score "$@"
        ;;
    score-all)
        cmd_score score-all
        ;;
    gate)
        shift
        cmd_score gate "$@"
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
