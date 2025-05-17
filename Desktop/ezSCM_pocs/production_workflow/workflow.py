import os
import uuid
from typing import Dict, Set, Optional, Any, List
from neo4j import GraphDatabase, Driver


class GoodNode:
    """
    Represents a material or product in the workflow.
    Prefixes: rg (Raw), ig (Intermediary), fg (Finished)
    """
    PREFIX_MAP = {"Raw": "rg", "Intermediary": "ig", "Finished": "fg"}

    def __init__(
        self,
        name: str,
        quantity: Optional[float] = None,
        unit: Optional[str] = None,
        good_type: str = "Raw",
        is_finished: bool = False
    ):
        prefix = self.PREFIX_MAP.get(good_type, "gd")
        self.id: str = f"{prefix}_{uuid.uuid4().hex}"
        self.name: str = name
        self.quantity: Optional[float] = quantity
        self.unit: Optional[str] = unit
        self.good_type: str = good_type
        self.is_finished: bool = is_finished
        self.used_in: Set["StageNode"] = set()
        self.made_from: Set["GoodNode"] = set()

    def __repr__(self) -> str:
        return f"{self.good_type}({self.name}, {self.quantity}{self.unit})"


class StageNode:
    """
    Represents a production stage in the workflow.
    """
    def __init__(
        self,
        number: int,
        production_time: str,
        outsource: str,
        wastage_entries: Dict[str, Dict[str, Any]]
    ):
        self.id: str = f"STG_{uuid.uuid4().hex}"
        self.number: int = number
        self.production_time: str = production_time
        self.outsource: str = outsource
        self.wastage_entries: Dict[str, Dict[str, Any]] = wastage_entries
        self.raw_inputs: Set[GoodNode] = set()
        self.intermediary_inputs: Set[GoodNode] = set()
        self.outputs: Set[GoodNode] = set()
        self.next_stage: Optional["StageNode"] = None

    def __repr__(self) -> str:
        return f"Stage({self.number})"


class ProductionGraph:
    """
    Builds and persists a stage-centric production workflow to Neo4j.
    Auto-loads Aura credentials from environment if not provided explicitly.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.stages: Dict[int, StageNode] = {}
        self.goods: Set[GoodNode] = set()
        self.name_map: Dict[str, GoodNode] = {}

        # Neo4j/Aura credentials
        self._uri = uri or os.getenv("NEO4J_URI")
        self._user = user or os.getenv("NEO4J_USERNAME")
        self._password = password or os.getenv("NEO4J_PASSWORD")
        self._driver: Optional[Driver] = None

    def _ensure_driver(self) -> Driver:
        if not self._driver:
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password)
            )
        return self._driver

    def get_or_create_good(
        self,
        name: str,
        quantity: Optional[float],
        unit: Optional[str],
        good_type: str,
        is_finished: bool
    ) -> GoodNode:
        if name in self.name_map:
            return self.name_map[name]
        node = GoodNode(name, quantity, unit, good_type, is_finished)
        self.goods.add(node)
        self.name_map[name] = node
        return node

    def add_stage(
        self,
        number: int,
        production_time: str,
        outsource: str,
        wastage_entries: Dict[str, Dict[str, Any]],
        raw_inputs: Set[GoodNode],
        intermediate_inputs: Set[GoodNode],
        outputs: Set[GoodNode]
    ) -> None:
        stage = StageNode(number, production_time, outsource, wastage_entries)
        stage.raw_inputs = raw_inputs
        stage.intermediary_inputs = intermediate_inputs
        stage.outputs = outputs

        # link goods <-> goods
        for out in outputs:
            for inp in raw_inputs | intermediate_inputs:
                out.made_from.add(inp)
                inp.used_in.add(out)

        self.stages[number] = stage

    def link_stages(self) -> None:
        for n in sorted(self.stages):
            if (n + 1) in self.stages:
                self.stages[n].next_stage = self.stages[n + 1]

    def load_from_json(self, data: Dict[str, Any]) -> None:
        stages_data = data.get("productionStages", [])
        max_stage = max(s["stageNumber"] for s in stages_data) if stages_data else None

        for s in stages_data:
            num = s["stageNumber"]
            det = s["productionDetails"]

            raw = {
                self.get_or_create_good(
                    r["goodName"], r.get("quantity"), r.get("unit"), "Raw", False
                ) for r in s.get("rawGoods", [])
            }

            outputs: Set[GoodNode] = set()
            for i, o in enumerate(s.get("outputGoods", [])):
                is_final = (num == max_stage and i == len(s["outputGoods"]) - 1)
                gt = "Finished" if is_final else "Intermediary"
                outputs.add(self.get_or_create_good(
                    o["goodName"], o.get("quantity"), o.get("unit"), gt, is_final
                ))

            wastage = {
                self.name_map[w["goodName"]].id: {
                    "wastage": w["wastage"],
                    "type": w["wastageType"]
                }
                for w in det.get("wastageEntries", [])
                if w["goodName"] in self.name_map
            }

            self.add_stage(
                num,
                det["productionTime"],
                det["outsource"],
                wastage,
                raw,
                set(),
                outputs
            )

        self.link_stages()
        self.save_to_neo4j()

    def save_to_neo4j(self) -> None:
        driver = self._ensure_driver()
        def _tx(tx):
            # create/merge stages
            for st in self.stages.values():
                tx.run(
                    """
                    MERGE (s:Stage {id:$id})
                    SET s.number = $num, s.name = $name, s.time = $time, s.outsource = $out, s.color = '#CCCCCC'
                    """,
                    id=st.id,
                    num=st.number,
                    name=f"Stage {st.number}",
                    time=st.production_time,
                    out=st.outsource
                )
            # create/merge goods
            for g in self.goods:
                label = f"{g.good_type}Good"
                color = {"Raw":"#ADD8E6","Intermediary":"#FFA500","Finished":"#FF4500"}[g.good_type]
                tx.run(
                    f"""
                    MERGE (n:Good:{label} {{id:$id}})
                    SET n.name = $name, n.quantity = $q, n.unit = $u, n.color = $col
                    """,
                    id=g.id, name=g.name, q=g.quantity, u=g.unit, col=color
                )
            # relationships
            for st in self.stages.values():
                for inp in st.raw_inputs | st.intermediary_inputs:
                    tx.run(
                        """
                        MATCH (n:Good {id:$gid}), (s:Stage {id:$sid})
                        MERGE (n)-[:USED_IN]->(s)
                        """,
                        gid=inp.id, sid=st.id
                    )
                for out in st.outputs:
                    tx.run(
                        """
                        MATCH (s:Stage {id:$sid}), (n:Good {id:$gid})
                        MERGE (s)-[:PRODUCES]->(n)
                        """,
                        sid=st.id, gid=out.id
                    )
                for gid, w in st.wastage_entries.items():
                    tx.run(
                        """
                        MATCH (n:Good {id:$gid})-[r:USED_IN]->(s:Stage {id:$sid})
                        SET r.wastage = $w, r.wastageType = $t
                        """,
                        gid=gid, sid=st.id, w=w["wastage"], t=w["type"]
                    )
        with driver.session() as session:
            session.write_transaction(_tx)

    def display(self) -> None:
        for num, st in sorted(self.stages.items()):
            raws = [g.name for g in st.raw_inputs]
            outs = [g.name for g in st.outputs]
            print(f"Stage {num}: RAW={raws}, OUT={outs}")


if __name__ == "__main__":
    # Example JSON as before
    example = {
        "productionStages": [
            # ... your stage definitions ...
        ]
    }
    g = ProductionGraph()
    g.load_from_json(example)
    g.display()
