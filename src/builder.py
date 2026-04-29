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
                    owner_id = p.owner
                    if not owner_id and p.parents:
                        # parentsフィールドの1番目を飼い主とみなす
                        owner_id = p.parents[0]
                    
                    if owner_id:
                        owner = self.person_map.get(owner_id)
                        if owner and owner.id in resolved:
                            p.level = owner.level
                            resolved.add(p.id)
                            progress = True
                        elif not owner:
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
                for p in self.persons:
                    if p.id not in resolved:
                        p.level = 0
                        resolved.add(p.id)
                break

    def _create_html_label(self, p: Person) -> str:
        # ... (変更なし) ...
        age_str = "年齢不明"
        if p.birthday:
            try:
                bday = datetime.strptime(p.birthday, "%Y-%m-%d").date()
                today = self.as_of_date
                if p.deathday:
                    try:
                        dday = datetime.strptime(p.deathday, "%Y-%m-%d").date()
                        age = dday.year - bday.year - ((dday.month, dday.day) < (bday.month, bday.day))
                        age_str = f"享年: {age}歳 ({p.birthday}生)"
                    except ValueError: pass
                else:
                    age = today.year - bday.year - ((today.month, today.day) < (bday.month, bday.day))
                    age_str = f"{age}歳 ({p.birthday}生)"
            except ValueError: pass

        img_row = ""
        if p.image_path:
            img_path = Path(p.image_path)
            if img_path.exists():
                img_row = f'<tr><td border="0" width="100" height="100" fixedsize="true"><img src="{p.image_path}" scale="true"/></td></tr>'

        reading_str = f'<tr><td border="0"><font point-size="10">{p.reading}</font></td></tr>' if p.reading else ""
        job_str = f'<tr><td border="0"><font point-size="10">職業: {p.job}</font></td></tr>' if self.show_job and p.job else ""

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
        dot.attr(rankdir="TB", splines="ortho", nodesep="1.0", ranksep="1.2")

        today_str = self.as_of_date.strftime("%Y-%m-%d")
        dot.attr(label=f"基準日: {today_str}  ", labelloc="t", labeljust="r", fontsize="10")

        couples: List[Tuple[str, str]] = []
        child_to_couple: Dict[str, Tuple[str, str]] = {}
        couple_to_children: Dict[Tuple[str, str], List[Person]] = {}
        person_to_pets: Dict[str, List[Person]] = {}

        for p in self.persons:
            if p.type == "pet":
                # 名前からIDを解決
                owner_name = p.owner or (p.parents[0] if p.parents else None)
                if owner_name:
                    owner_p = self.person_map.get(owner_name)
                    if owner_p:
                        person_to_pets.setdefault(owner_p.id, []).append(p)
                continue

            if len(p.parents) >= 2:
                p1, p2 = self.person_map.get(p.parents[0]), self.person_map.get(p.parents[1])
                if p1 and p2:
                    c = (p1.id, p2.id) if p1.sex == "male" or p2.sex == "female" else (p2.id, p1.id)
                    if c not in couples: couples.append(c)
                    child_to_couple[p.id] = c
                    couple_to_children.setdefault(c, []).append(p)

        ordered_levels: Dict[int, List[str]] = {}
        max_level = max((p.level for p in self.persons), default=0)
        
        # Level 0
        l0_order = []
        added = set()
        for c in couples:
            p1, p2 = self.id_map[c[0]], self.id_map[c[1]]
            if p1.level == 0 and p2.level == 0:
                for pid in [p1.id, p2.id]:
                    if pid not in added:
                        l0_order.append(pid)
                        added.add(pid)
                # 夫婦の後にペットを追加
                for pid in [p1.id, p2.id]:
                    for pet in person_to_pets.get(pid, []):
                        if pet.id not in added:
                            l0_order.append(pet.id)
                            added.add(pet.id)
        for p in self.persons:
            if p.level == 0 and p.id not in added:
                l0_order.append(p.id)
                added.add(p.id)
                for pet in person_to_pets.get(p.id, []):
                    if pet.id not in added:
                        l0_order.append(pet.id)
                        added.add(pet.id)
        ordered_levels[0] = l0_order

        # Level 1+
        for lv in range(1, max_level + 1):
            lv_order = []
            added = set()
            for parent_id in ordered_levels[lv - 1]:
                p_couples = [c for c in couples if parent_id in c]
                for c in p_couples:
                    if parent_id != c[0]: continue
                    children = couple_to_children.get(c, [])
                    children.sort(key=lambda x: (x.birthday or "9999-99-99", x.name))
                    for child in children:
                        if child.level == lv and child.id not in added:
                            partner_id = next((c_in[1] if child.id == c_in[0] else c_in[0] for c_in in couples if child.id in c_in), None)
                            if partner_id:
                                husb, wife = (child.id, partner_id) if child.sex == "male" else (partner_id, child.id)
                                for pid in [husb, wife]:
                                    if pid not in added:
                                        lv_order.append(pid)
                                        added.add(pid)
                                # 夫婦の後ろにまとめてペットを追加
                                for pid in [husb, wife]:
                                    for pet in person_to_pets.get(pid, []):
                                        if pet.id not in added:
                                            lv_order.append(pet.id)
                                            added.add(pet.id)
                            else:
                                lv_order.append(child.id)
                                added.add(child.id)
                                for pet in person_to_pets.get(child.id, []):
                                    if pet.id not in added:
                                        lv_order.append(pet.id)
                                        added.add(pet.id)
            for p in self.persons:
                if p.level == lv and p.id not in added:
                    lv_order.append(p.id)
                    added.add(p.id)
            ordered_levels[lv] = lv_order

        for lv in range(max_level + 1):
            nodes = ordered_levels.get(lv, [])
            
            # 人物ノードの階層
            with dot.subgraph(name=f"level_{lv}") as c_sub:
                c_sub.attr(rank="same")
                person_ids = [pid for pid in nodes if self.id_map[pid].type == "person"]
                
                for pid in person_ids:
                    p = self.id_map[pid]
                    bg = "#E6F2FF" if p.sex == "male" else "#FFE6E6" if p.sex == "female" else "#F0F0F0"
                    c_sub.node(pid, label=self._create_html_label(p), shape="box", style="filled,dashed" if p.deathday else "filled", fillcolor=bg)
                
                # 人物間の順序固定
                for i in range(len(person_ids) - 1):
                    is_couple = any((person_ids[i], person_ids[i+1]) == c or (person_ids[i+1], person_ids[i]) == c for c in couples)
                    c_sub.edge(person_ids[i], person_ids[i+1], style="invis", weight="10" if is_couple else "2")
                
                # 夫婦の結合ポイント（人物階層に配置）
                for h_id, w_id in couples:
                    if h_id in person_ids and w_id in person_ids:
                        f_id = f"F_{h_id}_{w_id}"
                        c_sub.node(f_id, shape="point", width="0.01", height="0.01")
                        c_sub.edge(h_id, f_id, dir="none", weight="5")
                        c_sub.edge(f_id, w_id, dir="none", weight="5")

            # 分岐ポイントおよびペットの階層（夫婦と子供の間）
            with dot.subgraph(name=f"level_{lv}_branch") as cb:
                cb.attr(rank="same")
                branch_nodes = []
                
                # 人物の並び順に基づいてブランチ階層のノードを作成
                for pid in person_ids:
                    # 1. 夫婦の分岐点（夫のIDが先に来た時だけ作成）
                    for husb_id, wife_id in couples:
                        if pid == husb_id and wife_id in person_ids:
                            b_id = f"B_{husb_id}_{wife_id}"
                            cb.node(b_id, shape="point", width="0.01", height="0.01")
                            branch_nodes.append(b_id)
                            # FからBへの垂直線
                            dot.edge(f"F_{husb_id}_{wife_id}", b_id, dir="none", weight="5")
                    
                    # 2. この人物のペット
                    for pet in person_to_pets.get(pid, []):
                        cb.node(pet.id, label=self._create_html_label(pet), shape="box", style="filled,rounded", fillcolor="#FFFFE0")
                        branch_nodes.append(pet.id)

                # ブランチ階層内の順序固定
                for i in range(len(branch_nodes) - 1):
                    cb.edge(branch_nodes[i], branch_nodes[i+1], style="invis", weight="2")

        # 7. 実線の接続（親子）
        for p in self.persons:
            if p.type == "person" and p.id in child_to_couple:
                c = child_to_couple[p.id]
                dot.edge(f"B_{c[0]}_{c[1]}", p.id, dir="forward")

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
