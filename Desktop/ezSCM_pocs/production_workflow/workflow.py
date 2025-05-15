import uuid
from neo4j import GraphDatabase

# -------------------------------
# Node definitions with unique ID prefixes
# -------------------------------

class GoodNode:
    PREFIX_MAP = {"Raw": "RG", "Intermediary": "IG", "Finished": "FG"}

    def __init__(self, name, quantity=None, unit=None, good_type="Raw", is_finished=False):
        prefix = GoodNode.PREFIX_MAP.get(good_type, "GD")
        self.id = f"{prefix}_{uuid.uuid4().hex}"
        self.name = name
        self.quantity = quantity
        self.unit = unit
        self.good_type = good_type
        self.is_finished = is_finished
        self.used_in = set()
        self.made_from = set()

    def __repr__(self):
        return f"{self.good_type}({self.name}, {self.quantity}{self.unit})"


class StageNode:
    def __init__(self, number, production_time, outsource, wastage_entries):
        self.id = f"STG_{uuid.uuid4().hex}"
        self.number = number
        self.production_time = production_time
        self.outsource = outsource
        self.wastage_entries = wastage_entries  # {good_id: {wastage, type}}
        self.raw_inputs = set()
        self.intermediary_inputs = set()
        self.outputs = set()
        self.next_stage = None

    def __repr__(self):
        return f"Stage({self.number})"


# -------------------------------
# ProductionGraph with cleaned relationships
# -------------------------------

class ProductionGraph:
    def __init__(self):
        self.stages = {}        # stage_number -> StageNode
        self.goods = set()      # set of GoodNode
        self.name_map = {}      # name -> GoodNode

    def get_or_create_good(self, name, quantity=None, unit=None, good_type="Raw", is_finished=False):
        if name in self.name_map:
            return self.name_map[name]
        node = GoodNode(name, quantity, unit, good_type, is_finished)
        self.goods.add(node)
        self.name_map[name] = node
        return node

    def add_stage(self, number, production_time, outsource, wastage_entries, raw_inputs, intermediary_inputs, outputs):
        stage = StageNode(number, production_time, outsource, wastage_entries)
        stage.raw_inputs = set(raw_inputs)
        stage.intermediary_inputs = set(intermediary_inputs)
        stage.outputs = set(outputs)
        for out in outputs:
            for inp in raw_inputs.union(intermediary_inputs):
                out.made_from.add(inp)
                inp.used_in.add(out)
        self.stages[number] = stage

    def link_stages(self):
        for num in sorted(self.stages):
            if num + 1 in self.stages:
                self.stages[num].next_stage = self.stages[num + 1]

    def load_from_json(self, json_obj):
        for stage_data in json_obj.get("productionStages", []):
            num = stage_data["stageNumber"]
            details = stage_data["productionDetails"]
            raw_nodes, interm_nodes = set(), set()
            for raw in stage_data["rawGoods"]:
                node = self.get_or_create_good(raw["goodName"], raw.get("quantity"), raw.get("unit"), "Raw")
                (interm_nodes if node.good_type != "Raw" else raw_nodes).add(node)
            out_nodes = set()
            for out in stage_data["outputGoods"]:
                is_final = out["goodName"].lower() == "bread & omlet"
                node = self.get_or_create_good(out["goodName"], out.get("quantity"), out.get("unit"), "Intermediary", is_final)
                out_nodes.add(node)
            wastage_entries = {}
            for w in details.get("wastageEntries", []):
                gnode = self.name_map.get(w["goodName"])
                if gnode:
                    wastage_entries[gnode.id] = {"wastage": w["wastage"], "type": w["wastageType"]}
            self.add_stage(num, details.get("productionTime"), details.get("outsource"), wastage_entries, raw_nodes, interm_nodes, out_nodes)
        self.link_stages()

    def save_to_neo4j(self, uri, user, password):
        driver = GraphDatabase.driver(uri, auth=(user, password))
        def tx_func(tx):
            for st in self.stages.values():
                tx.run(
                    "MERGE (s:Stage {id:$id}) SET s.number=$num, s.name='Stage '+toString($num), s.time=$t, s.outsource=$o, s.color='#CCCCCC'",
                    id=st.id, num=st.number, t=st.production_time, o=st.outsource
                )
            for g in self.goods:
                label = g.good_type + "Good"
                color = {'Raw':'#ADD8E6','Intermediary':'#FFA500','Finished':'#FF4500'}[g.good_type]
                tx.run(
                    f"MERGE (n:Good:{label} {{id:$id}}) SET n.name=$name, n.quantity=$q, n.unit=$u, n.color='{color}'",
                    id=g.id, name=g.name, q=g.quantity, u=g.unit
                )
            for st in self.stages.values():
                for inp in st.raw_inputs.union(st.intermediary_inputs):
                    tx.run(
                        "MATCH (n:Good {id:$gid}), (s:Stage {id:$sid}) MERGE (n)-[:USED_IN]->(s)",
                        gid=inp.id, sid=st.id
                    )
                for out in st.outputs:
                    tx.run(
                        "MATCH (s:Stage {id:$sid}), (n:Good {id:$gid}) MERGE (s)-[:PRODUCES]->(n)",
                        sid=st.id, gid=out.id
                    )
                for gid, w in st.wastage_entries.items():
                    tx.run(
                        "MATCH (n:Good {id:$gid})-[r:USED_IN]->(s:Stage {id:$sid}) SET r.wastage=$w, r.wastageType=$t",
                        gid=gid, sid=st.id, w=w['wastage'], t=w['type']
                    )
        with driver.session() as session:
            session.write_transaction(tx_func)
        driver.close()

    def display(self):
        for num, st in sorted(self.stages.items()):
            print(f"Stage {num}: RAW={[g.name for g in st.raw_inputs]}, OUT={[g.name for g in st.outputs]}")

# -------------------------------
# Example Usage
# -------------------------------
if __name__=='__main__':
    example_json = {
    "productionStages": [
        {
            "stageNumber": 1,
            "rawGoods": [
                {"goodName": "Wheat", "quantity": 100, "unit": "kg"},
                {"goodName": "Water", "quantity": 50, "unit": "L"}
            ],
            "productionDetails": {
                "wastageEntries": [],
                "productionTime": "2h",
                "outsource": "No"
            },
            "outputGoods": [
                {"goodName": "Dough", "quantity": 140, "unit": "kg"}
            ]
        },
        {
            "stageNumber": 2,
            "rawGoods": [
                {"goodName": "Dough", "quantity": 140, "unit": "kg"},
                {"goodName": "Yeast", "quantity": 5, "unit": "kg"}
            ],
            "productionDetails": {
                "wastageEntries": [],
                "productionTime": "1.5h",
                "outsource": "No"
            },
            "outputGoods": [
                {"goodName": "Bread", "quantity": 135, "unit": "kg"}
            ]
        },
        {
            "stageNumber": 3,
            "rawGoods": [
                {"goodName": "Eggs", "quantity": 60, "unit": "pcs"},
                {"goodName": "Water", "quantity": 20, "unit": "L"}
            ],
            "productionDetails": {
                "wastageEntries": [],
                "productionTime": "1h",
                "outsource": "No"
            },
            "outputGoods": [
                {"goodName": "Omlet", "quantity": 60, "unit": "pcs"}
            ]
        },
        {
            "stageNumber": 4,
            "rawGoods": [
                {"goodName": "Bread", "quantity": 135, "unit": "kg"},
                {"goodName": "Omlet", "quantity": 60, "unit": "pcs"}
            ],
            "productionDetails": {
                "wastageEntries": [],
                "productionTime": "0.5h",
                "outsource": "No"
            },
            "outputGoods": [
                {"goodName": "Bread & Omlet", "quantity": 195, "unit": "units"}
            ]
        }
    ]
}
    g = ProductionGraph()
    g.load_from_json(example_json)
    g.save_to_neo4j("bolt://localhost:7687","neo4j","12345678")
    g.display()
