import argparse
from datetime import date, datetime
from pathlib import Path

from src.builder import GraphBuilder, embed_images_in_svg
from src.parser import load_yaml_data


def main():
    parser = argparse.ArgumentParser(
        description="YAML定義ファイルから家系図（SVG）を生成します。"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="sample.yaml",
        help="入力YAMLファイルのパス (デフォルト: sample.yaml)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="出力ファイル名（拡張子なし）。 (デフォルト: 入力ファイル名と同じ)",
    )
    parser.add_argument(
        "--format",
        "-f",
        default="svg",
        help="出力フォーマット (svg, pdf, png, etc.) (デフォルト: svg)",
    )
    parser.add_argument(
        "--hide-job",
        action="store_true",
        help="ノード内の職業情報を非表示にします",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        metavar="YYYY-MM-DD",
        help="年齢計算の基準日を指定します（省略時はスクリプト実行日）",
    )

    args = parser.parse_args()

    # 基準日の解決
    as_of_date: date
    if args.as_of:
        try:
            as_of_date = datetime.strptime(args.as_of, "%Y-%m-%d").date()
        except ValueError:
            print(
                f"Error: --as-of の日付フォーマットが不正です: '{args.as_of}'. YYYY-MM-DD 形式で指定してください。"
            )
            return
    else:
        as_of_date = date.today()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: 入力ファイル '{args.input}' が見つかりません。")
        return

    # 1. YAML を解析
    persons = load_yaml_data(str(input_path))
    print(f"{args.input} から {len(persons)} 件のデータを読み込みました")

    # 2. グラフを構築
    builder = GraphBuilder(persons, show_job=not args.hide_job, as_of_date=as_of_date, output_format=args.format)
    dot = builder.build()

    # 3. レンダリング
    # 出力ベース名の決定（指定がなければ入力ファイル名を使用）
    if args.output:
        output_base = args.output
    else:
        output_base = input_path.stem

    # 出力ファイル名から指定されたフォーマットの拡張子を除去（もしあれば）
    if output_base.endswith(f".{args.format}"):
        output_base = output_base[:-(len(args.format) + 1)]
    
    output_path = dot.render(output_base, cleanup=True)

    # 4. SVG の場合のみ、画像を Base64 に埋め込んで自己完結させる
    if args.format.lower() == "svg":
        embed_images_in_svg(output_path)

    print(f"家系図を生成しました: {output_path}  (基準日: {as_of_date})")


if __name__ == "__main__":
    main()
