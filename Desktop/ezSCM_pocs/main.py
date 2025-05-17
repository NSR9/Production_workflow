import os
import io
import sys
import uuid
from typing import List, Dict, Any, Set, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from neo4j import GraphDatabase

app = FastAPI(title="Stage-Centric Production Workflow API — Neo4j Aura only")

# Neo4j Aura configuration
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://08aae6b5.databases.neo4j.io")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "0g6cqKCmb3fOISxP6-J2cy-IwgyQn32NzfTm3ABtYxA")

# -------------------------------
# Workflow graph classes
# -------------------------------

class GoodNode:
    PREFIX_MAP = {"Raw": "rg", "Intermediary": "ig", "Finished": "fg"}

    def __init__(self,
                 name: str,
                 quantity: Optional[float] = None,
                 unit: Optional[str] = None,
                 good_type: str = "Raw",
                 is_finished: bool = False):
        prefix = self.PREFIX_MAP.get(good_type, "gd")
        self.id: str = f"{prefix}_{uuid.uuid4().hex}"
        self.name: str = name
        self.quantity: Optional[float] = quantity
        self.unit: Optional[str] = unit
        self.good_type: str = good_type
        self.is_finished: bool = is_finished
        self.used_in: Set['StageNode'] = set()
        self.made_from: Set['GoodNode'] = set()

    def __repr__(self) -> str:
        return f"{self.good_type}({self.name}, {self.quantity}{self.unit})"


class StageNode:
    def __init__(self,
                 number: int,
                 production_time: str,
                 outsource: str,
                 wastage_entries: Dict[str, Dict[str, Any]]):
        self.id: str = f"STG_{uuid.uuid4().hex}"
        self.number: int = number
        self.production_time: str = production_time
        self.outsource: str = outsource
        self.wastage_entries: Dict[str, Dict[str, Any]] = wastage_entries
        self.raw_inputs: Set[GoodNode] = set()
        self.intermediary_inputs: Set[GoodNode] = set()
        self.outputs: Set[GoodNode] = set()
        self.next_stage: Optional['StageNode'] = None

    def __repr__(self) -> str:
        return f"Stage({self.number})"


class ProductionGraph:
    def __init__(self,
                 uri: Optional[str] = None,
                 user: Optional[str] = None,
                 password: Optional[str] = None):
        self.stages: Dict[int, StageNode] = {}
        self.goods: Set[GoodNode] = set()
        self.name_map: Dict[str, GoodNode] = {}

        # Neo4j/Aura credentials
        self._uri = uri or NEO4J_URI
        self._user = user or NEO4J_USERNAME
        self._password = password or NEO4J_PASSWORD
        self._driver = None

    def _ensure_driver(self):
        if not self._driver:
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password)
            )
        return self._driver

    def clear_db(self) -> None:
        driver = self._ensure_driver()
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def get_or_create_good(self,
                           name: str,
                           quantity: Optional[float],
                           unit: Optional[str],
                           good_type: str,
                           is_finished: bool) -> GoodNode:
        if name in self.name_map:
            return self.name_map[name]
        node = GoodNode(name, quantity, unit, good_type, is_finished)
        self.goods.add(node)
        self.name_map[name] = node
        return node

    def add_stage(self,
                  number: int,
                  production_time: str,
                  outsource: str,
                  wastage_entries: Dict[str, Dict[str, Any]],
                  raw_inputs: Set[GoodNode],
                  intermediary_inputs: Set[GoodNode],
                  outputs: Set[GoodNode]) -> None:
        stage = StageNode(number, production_time, outsource, wastage_entries)
        stage.raw_inputs = raw_inputs
        stage.intermediary_inputs = intermediary_inputs
        stage.outputs = outputs

        for out in outputs:
            for inp in raw_inputs | intermediary_inputs:
                out.made_from.add(inp)
                inp.used_in.add(out)

        self.stages[number] = stage

    def link_stages(self) -> None:
        for num in sorted(self.stages):
            if num + 1 in self.stages:
                self.stages[num].next_stage = self.stages[num + 1]

    def load_from_json(self, data: Dict[str, Any]) -> None:
        stages_data = data.get("productionStages", [])
        max_stage = max(s["stageNumber"] for s in stages_data) if stages_data else None

        for s in stages_data:
            num = s["stageNumber"]
            det = s["productionDetails"]

            raw_set = {
                self.get_or_create_good(
                    r["goodName"], r.get("quantity"), r.get("unit"), "Raw", False
                ) for r in s.get("rawGoods", [])
            }

            out_set: Set[GoodNode] = set()
            for i, o in enumerate(s.get("outputGoods", [])):
                is_fin = (num == max_stage and i == len(s["outputGoods"]) - 1)
                gt = "Finished" if is_fin else "Intermediary"
                out_set.add(
                    self.get_or_create_good(
                        o["goodName"], o.get("quantity"), o.get("unit"), gt, is_fin
                    )
                )

            wastage = {
                self.name_map[w["goodName"]].id: {"wastage": w["wastage"], "type": w["wastageType"]}
                for w in det.get("wastageEntries", [])
                if w["goodName"] in self.name_map
            }

            self.add_stage(num, det["productionTime"], det["outsource"], wastage, raw_set, set(), out_set)

        self.link_stages()
        self.save_to_neo4j()

    def save_to_neo4j(self) -> None:
        driver = self._ensure_driver()
        def tx(tx):
            for st in self.stages.values():
                tx.run(
                    "MERGE (s:Stage {id:$id}) "
                    "SET s.number=$num, s.name=$name, s.time=$time, s.outsource=$out, s.color='#CCCCCC'",
                    id=st.id, num=st.number, name=f"Stage {st.number}", time=st.production_time, out=st.outsource
                )
            for g in self.goods:
                label = f"{g.good_type}Good"
                color = {'Raw':'#ADD8E6','Intermediary':'#FFA500','Finished':'#FF4500'}[g.good_type]
                tx.run(
                    f"MERGE (n:Good:{label} {{id:$id}}) "
                    "SET n.name=$name, n.quantity=$q, n.unit=$u, n.color=$col",
                    id=g.id, name=g.name, q=g.quantity, u=g.unit, col=color
                )
            for st in self.stages.values():
                for inp in st.raw_inputs | st.intermediary_inputs:
                    tx.run(
                        "MATCH (n:Good {id:$gid}), (s:Stage {id:$sid}) "
                        "MERGE (n)-[:USED_IN]->(s)",
                        gid=inp.id, sid=st.id
                    )
                for out in st.outputs:
                    tx.run(
                        "MATCH (s:Stage {id:$sid}), (n:Good {id:$gid}) "
                        "MERGE (s)-[:PRODUCES]->(n)",
                        sid=st.id, gid=out.id
                    )
                for gid, w in st.wastage_entries.items():
                    tx.run(
                        "MATCH (n:Good {id:$gid})-[r:USED_IN]->(s:Stage {id:$sid}) "
                        "SET r.wastage=$w, r.wastageType=$t",
                        gid=gid, sid=st.id, w=w['wastage'], t=w['type']
                    )
        with driver.session() as session:
            session.write_transaction(tx)

    def display(self) -> None:
        for num, st in sorted(self.stages.items()):
            raws = [g.name for g in st.raw_inputs]
            outs = [g.name for g in st.outputs]
            print(f"Stage {num}: RAW={raws}, OUT={outs}")


# -------------------------------
# Pydantic request model
# -------------------------------

class WastageEntryModel(BaseModel):
    goodName: str
    wastage: float
    wastageType: str

class GoodEntryModel(BaseModel):
    goodName: str
    quantity: float
    unit: str

class ProductionDetailsModel(BaseModel):
    wastageEntries: List[WastageEntryModel]
    productionTime: str
    outsource: str

class StageModel(BaseModel):
    stageNumber: int
    rawGoods: List[GoodEntryModel]
    outputGoods: List[GoodEntryModel]
    productionDetails: ProductionDetailsModel

class WorkflowCreateModel(BaseModel):
    productionStages: List[StageModel]


@app.get("/", response_model=dict)
async def read_root():
    return {"message": "Production Workflow API — Neo4j only"}

@app.post(
    "/workflows",
    status_code=status.HTTP_201_CREATED,
    response_model=dict
)
async def create_stage_workflow(workflow: WorkflowCreateModel):
    try:
        graph = ProductionGraph()
        graph.clear_db()                     # remove old data
        graph.load_from_json(workflow.dict())  # build & save new

        buffer = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buffer
        graph.display()
        sys.stdout = old_stdout

        return {
            "saved_at": datetime.utcnow(),
            "display": buffer.getvalue().splitlines()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error saving or displaying workflow: {e}"
        )
