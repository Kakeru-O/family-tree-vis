import hashlib
from dataclasses import dataclass, field
from typing import List, Optional

import yaml


@dataclass
class Person:
    name: str
    reading: str = ""
    sex: str = ""
    birthday: str = ""
    deathday: Optional[str] = None
    job: str = ""
    image_path: str = ""
    parents: List[str] = field(default_factory=list)
    type: str = "person"  # person or pet
    owner: Optional[str] = None
    spouse: Optional[str] = None

    # 計算で決まるプロパティ
    level: int = 0
    id: str = ""

    def __post_init__(self):
        # 同姓同名などを区別するため、名前と誕生日ベースでIDを割り当てる
        if not self.id:
            raw = f"{self.name}_{self.birthday}_{self.type}".encode()
            self.id = "N_" + hashlib.md5(raw).hexdigest()[:8]


def load_yaml_data(filepath: str) -> List[Person]:
    """YAMLファイルを読み込み、Personオブジェクトのリストを返す"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    people_data = data.get("people", [])
    persons = []

    # 割り当て用の一意IDカウンタ
    unknown_counter = 1

    for p_dict in people_data:
        name = p_dict.get("name", "不明")
        if name == "不明":
            name = f"不明_{unknown_counter}"
            unknown_counter += 1

        person = Person(
            name=name,
            reading=p_dict.get("reading", ""),
            sex=p_dict.get("sex", ""),
            birthday=p_dict.get("birthday", ""),
            deathday=p_dict.get("deathday"),
            job=p_dict.get("job", ""),
            image_path=p_dict.get("image_path", ""),
            parents=p_dict.get("parents", []),
            type=p_dict.get("type", "person"),
            owner=p_dict.get("owner"),
            spouse=p_dict.get("spouse"),
        )
        persons.append(person)

    return persons
