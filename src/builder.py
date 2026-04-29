import base64
import mimetypes
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

import graphviz

from .parser import Person


class GraphBuilder:
    def __init__(
        self, persons: List[Person], show_job: bool = True, as_of_date: date = None
    ):
        self.persons = persons
        self.person_map: Dict[str, Person] = {}
        self.id_map: Dict[str, Person] = {}
        self.temp_images: List[str] = []
        self.show_job = show_job
        self.as_of_date: date = as_of_date or date.today()

        for p in persons:
            self.person_map[p.name] = p
            self.id_map[p.id] = p

        self._calculate_levels()

    def _calculate_levels(self):
        """トポロジカルソート的に、親から子へのLevel(Rank)を計算する"""
        partner_map: Dict[str, str] = {}
        for p in self.persons:
            if p.type == "person" and len(p.parents) >= 2:
                parent1 = self.person_map.get(p.parents[0])
                parent2 = self.person_map.get(p.parents[1])
                if parent1 and parent2:
                    partner_map[parent1.id] = parent2.id
                    partner_map[parent2.id] = parent1.id

        resolved = set()
        while len(resolved) < len(self.persons):
            progress = False
            for p in self.persons:
                if p.id in resolved:
                    continue

                # ペットのレベルは飼い主と同じにする
                if p.type == "pet":
                    if p.owner:
                        owner = self.person_map.get(p.owner)
                        if owner and owner.id in resolved:
                            p.level = owner.level
                            resolved.add(p.id)
                            progress = True
                        elif not owner:
                            # 飼い主が見つからない場合はLevel 0
                            p.level = 0
                            resolved.add(p.id)
                            progress = True
                    else:
                        p.level = 0
                        resolved.add(p.id)
                        progress = True
                    continue

                if not p.parents:
                    partner_id = partner_map.get(p.id)
                    if partner_id and partner_id in resolved:
                        p.level = self.id_map[partner_id].level
                        resolved.add(p.id)
                        progress = True
                    else:
                        if partner_id and self.id_map[partner_id].parents:
                            # 配偶者が親を持つ場合は、配偶者のレベルが先に決まるのを待つ
                            continue
                        p.level = 0
                        resolved.add(p.id)
                        progress = True
                else:
                    all_parents_resolved = True
                    max_parent_level = -1
                    for parent_name in p.parents:
                        parent = self.person_map.get(parent_name)
                        if parent and parent.id in resolved:
                            max_parent_level = max(max_parent_level, parent.level)
                        elif parent:
                            all_parents_resolved = False
                            break
                    if all_parents_resolved:
                        p.level = max_parent_level + 1
                        resolved.add(p.id)
                        progress = True

            if not progress:
                print(
                    "Warning: 循環参照があるか、解決できない親関係が存在します。残りのノードはLevel 0とし強制解決します。"
                )
                for p in self.persons:
                    if p.id not in resolved:
                        p.level = 0
                        resolved.add(p.id)
                break

    def _create_html_label(self, p: Person) -> str:
        age_str = "年齢不明"
        if p.birthday:
            try:
                bday = datetime.strptime(p.birthday, "%Y-%m-%d").date()
                # 指定された基準日（または実行日）を使って年齢計算
                today = self.as_of_date

                if p.deathday:
                    try:
                        dday = datetime.strptime(p.deathday, "%Y-%m-%d").date()
                        age = (
                            dday.year
                            - bday.year
                            - ((dday.month, dday.day) < (bday.month, bday.day))
                        )
                        age_str = f"享年: {age}歳 ({p.birthday}生)"
                    except ValueError:
                        pass
                else:
                    age = (
                        today.year
                        - bday.year
                        - ((today.month, today.day) < (bday.month, bday.day))
                    )
                    age_str = f"{age}歳 ({p.birthday}生)"
            except ValueError:
                pass

        img_row = ""
        if p.image_path:
            img_path = Path(p.image_path)
            if img_path.exists():
                # Graphvizは長いData URIをファイル名として扱おうとして失敗するため、
                # レンダリング時は元のファイルパスを使い、後でSVGを加工して埋め込む
                img_row = f'<tr><td border="0" width="100" height="100" fixedsize="true"><img src="{p.image_path}" scale="true"/></td></tr>'

        reading_str = (
            f'<tr><td border="0"><font point-size="10">{p.reading}</font></td></tr>'
            if p.reading
            else ""
        )
        job_str = (
            f'<tr><td border="0"><font point-size="10">職業: {p.job}</font></td></tr>'
            if self.show_job and p.job
            else ""
        )

        label = f"""<<table border="0" cellborder="0" cellspacing="0">
{img_row}
{reading_str}
<tr><td border="0"><b>{p.name}</b></td></tr>
<tr><td border="0"><font point-size="10">{age_str}</font></td></tr>
{job_str}
</table>>"""
        return label

    def build(self) -> graphviz.Digraph:
        dot = graphviz.Digraph(comment="Family Tree", format="svg")
        # スタイル設定: 上から下へ, 直角接続
        dot.attr(rankdir="TB", splines="ortho", nodesep="0.6", ranksep="0.8")

        # 生成日・基準日を右上に表示
        today_str = self.as_of_date.strftime("%Y-%m-%d")
        dot.attr(
            label=f"基準日: {today_str}  ", labelloc="t", labeljust="r", fontsize="10"
        )

        # 夫婦ペアの抽出
        couples: Set[Tuple[str, str]] = set()
        child_to_couple: Dict[str, Tuple[str, str]] = {}

        for p in self.persons:
            if p.type == "person" and len(p.parents) >= 2:
                parent1 = self.person_map.get(p.parents[0])
                parent2 = self.person_map.get(p.parents[1])
                if parent1 and parent2:
                    if parent1.sex == "male" or parent2.sex == "female":
                        c = (parent1.id, parent2.id)
                    else:
                        c = (parent2.id, parent1.id)
                    couples.add(c)
                    child_to_couple[p.id] = c

        # レベルごとにSubGraphを作成
        levels_map: Dict[int, List[Person]] = {}
        for p in self.persons:
            levels_map.setdefault(p.level, []).append(p)

        for level, people_in_level in levels_map.items():
            # 通常ノード（人間）
            with dot.subgraph(name=f"level_{level}") as c:
                c.attr(rank="same")
                for p in people_in_level:
                    if p.type != "person":
                        continue
                    bg_color = (
                        "#E6F2FF"
                        if p.sex == "male"
                        else "#FFE6E6"
                        if p.sex == "female"
                        else "#F0F0F0"
                    )
                    style = "filled,dashed" if p.deathday else "filled"
                    c.node(
                        p.id,
                        label=self._create_html_label(p),
                        shape="box",
                        style=style,
                        fillcolor=bg_color,
                        margin="0.1",
                    )

                # 兄弟の並び順を固定
                couple_to_children = {}
                for p in people_in_level:
                    if p.id in child_to_couple:
                        c_tuple = child_to_couple[p.id]
                        couple_to_children.setdefault(c_tuple, []).append(p)

                for children in couple_to_children.values():
                    # 誕生日順にソート（不明な場合は名前順）
                    children.sort(key=lambda x: (x.birthday or "9999-99-99", x.name))
                    for i in range(len(children) - 1):
                        # 同じランク内で左から右への順序を強制（weightを重くして安定させる）
                        c.edge(children[i].id, children[i + 1].id, style="invis", weight="2")

                # 夫婦の接続
                for husb_id, wife_id in couples:
                    h = self.id_map.get(husb_id)
                    w = self.id_map.get(wife_id)
                    if h and w and h.level == level and w.level == level:
                        f_node_id = f"F_{husb_id}_{wife_id}"
                        c.node(f_node_id, shape="point", width="0.01", height="0.01")
                        if h.sex == "male":
                            male_id, female_id = h.id, w.id
                        elif w.sex == "male":
                            male_id, female_id = w.id, h.id
                        else:
                            male_id, female_id = h.id, w.id
                        c.edge(male_id, f_node_id, dir="none")
                        c.edge(f_node_id, female_id, dir="none")

            # 分岐点およびペットのレイヤー
            with dot.subgraph(name=f"level_{level}_branch") as c_branch:
                c_branch.attr(rank="same")
                for husb_id, wife_id in couples:
                    h = self.id_map.get(husb_id)
                    if h and h.level == level:
                        b_node_id = f"B_{husb_id}_{wife_id}"
                        c_branch.node(
                            b_node_id, shape="point", width="0.01", height="0.01"
                        )
                        dot.edge(f"F_{husb_id}_{wife_id}:s", b_node_id, dir="none")

                # ペットのノードをこのレイヤーに配置
                for p in people_in_level:
                    if p.type == "pet":
                        # ペットは角丸、薄い黄色
                        style = "filled,rounded"
                        bg_color = "#FFFFE0"
                        c_branch.node(
                            p.id,
                            label=self._create_html_label(p),
                            shape="box",
                            style=style,
                            fillcolor=bg_color,
                            margin="0.1",
                        )

        # 子どもへのエッジ
        for p in self.persons:
            if p.type == "pet":
                continue
            if p.id in child_to_couple:
                couple = child_to_couple[p.id]
                b_node_id = f"B_{couple[0]}_{couple[1]}"
                # ポート指定を外して、Graphvizに自由なルート（直角）を選ばせる
                dot.edge(b_node_id, p.id, dir="forward")
            elif p.parents:
                parent = self.person_map.get(p.parents[0])
                if parent:
                    dot.edge(parent.id, p.id, dir="forward")

        return dot


def embed_images_in_svg(svg_path: str):
    """SVGファイル内の画像パスをBase64データURIに置換する"""
    with open(svg_path, "r", encoding="utf-8") as f:
        content = f.read()

    import re

    # <image ... xlink:href="path/to/img" ... /> を探す
    pattern = r'(<image[^>]+(?:xlink:href|href)=")([^"]+)(")'

    def replacer(match):
        prefix, img_rel_path, suffix = match.groups()
        img_path = Path(img_rel_path)
        if img_path.exists():
            with open(img_path, "rb") as img_f:
                encoded = base64.b64encode(img_f.read()).decode("utf-8")
            mime_type, _ = mimetypes.guess_type(str(img_path))
            mime_type = mime_type or "image/png"
            return f"{prefix}data:{mime_type};base64,{encoded}{suffix}"
        return match.group(0)

    new_content = re.sub(pattern, replacer, content)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(new_content)
