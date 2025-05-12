import uuid
import networkx as nx
import matplotlib.pyplot as plt
import graphviz
# -------------------------------
# Simplified GoodNode and StageNode
# -------------------------------

class GoodNode:
    def __init__(self, name, quantity=None, unit=None, good_type="Raw", is_finished=False):
        self.id = f"{good_type[:2].upper()}_{uuid.uuid4().hex}"
        self.name = name
        self.quantity = quantity
        self.unit = unit
        self.good_type = good_type  # "Raw" or "Intermediary"
        self.is_finished = is_finished
        self.used_in = set()
        self.made_from = set()

    def __repr__(self):
        return f"{self.good_type}({self.name}, {self.quantity}{self.unit})"


class StageNode:
    def __init__(self, number, production_time, outsource, wastage_entries):
        self.number = number
        self.production_time = production_time
        self.outsource = outsource
        self.wastage_entries = wastage_entries  # Dict[good_id] = {'wastage': value, 'type': '%|unit'}
        self.raw_inputs = set()
        self.intermediary_inputs = set()
        self.outputs = set()
        self.next_stage = None

    def __repr__(self):
        return f"Stage({self.number})"


# -------------------------------
# Simplified ProductionGraph
# -------------------------------

class ProductionGraph:
    def get_id_by_name(self, name):
        node = next((n for n in self.goods if n.name == name), None)
        return node.id if node else None

    def __init__(self):
        self.stages = {}  # stage_number -> StageNode
        self.goods = set()

    def create_good(self, name, quantity=None, unit=None, good_type="Raw", is_finished=False):
        node = GoodNode(name, quantity, unit, good_type, is_finished)
        self.goods.add(node)
        return node

    def mark_as_finished(self, node):
        node.is_finished = True

    def add_stage(self, number, production_time, outsource, wastage_entries,
                  raw_inputs, intermediary_inputs, outputs):
        stage = StageNode(number, production_time, outsource, wastage_entries)
        stage.raw_inputs.update(raw_inputs)
        stage.intermediary_inputs.update(intermediary_inputs)
        stage.outputs.update(outputs)

        for out in outputs:
            for inp in raw_inputs.union(intermediary_inputs):
                out.made_from.add(inp)
                inp.used_in.add(out)

        self.stages[number] = stage

    def link_stages(self):
        for i in sorted(self.stages):
            if i + 1 in self.stages:
                self.stages[i].next_stage = self.stages[i + 1]

    def display(self):
        print("\n📦 Simplified Production Workflow")
        for num in sorted(self.stages):
            stage = self.stages[num]
            print(f"\n🔄 Stage {num}:")
            print("  ⏱ Time:", stage.production_time)
            print("  🔧 Outsource:", stage.outsource)
            print("  🧪 Wastage:")
            for gid, entry in stage.wastage_entries.items():
                good = next((g for g in self.goods if g.id == gid), None)
                if good:
                    print(f"    - {good.name}: {entry['wastage']}{entry['type']}")

            print("  🔹 Raw Inputs:")
            for g in stage.raw_inputs:
                print(f"    - {g.name} ({g.quantity}{g.unit})")

            print("  🔸 Intermediary Inputs:")
            for g in stage.intermediary_inputs:
                print(f"    - {g.name} ({g.quantity}{g.unit})")

            print("  🏁 Outputs:")
            for g in stage.outputs:
                from_ = ', '.join(i.name for i in g.made_from)
                print(f"    - {g.name} ← {from_}")

        finished = [g for g in self.goods if g.is_finished]
        if finished:
            print("\n✅ Finished Goods:")
            for g in finished:
                from_ = ', '.join(i.name for i in g.made_from)
                print(f"  {g.name} ← {from_}")

    def load_from_json(self, json_obj):
        name_to_node = {}
        for stage_data in json_obj["productionStages"]:
            stage_number = stage_data["stageNumber"]
            production_time = stage_data["productionDetails"]["productionTime"]
            outsource = stage_data["productionDetails"]["outsource"]
            wastage_entries_raw = stage_data["productionDetails"].get("wastageEntries", [])

            raw_nodes = set()
            for raw in stage_data["rawGoods"]:
                node = self.create_good(raw["goodName"], raw["quantity"], raw["unit"], good_type="Raw")
                name_to_node[raw["goodName"]] = node
                raw_nodes.add(node)

            output_nodes = set()
            for out in stage_data["outputGoods"]:
                node = self.create_good(out["goodName"], out["quantity"], out["unit"], good_type="Intermediary")
                name_to_node[out["goodName"]] = node
                output_nodes.add(node)

            intermediary_inputs = set()
            for raw in stage_data["rawGoods"]:
                if raw["goodName"] in name_to_node and name_to_node[raw["goodName"]].good_type == "Intermediary":
                    intermediary_inputs.add(name_to_node[raw["goodName"]])

            wastage_entries = {}
            for entry in wastage_entries_raw:
                good = name_to_node.get(entry["goodName"])
                if good:
                    wastage_entries[good.id] = {
                        "wastage": entry["wastage"],
                        "type": entry["wastageType"]
                    }

            self.add_stage(stage_number, production_time, outsource, wastage_entries, raw_nodes, intermediary_inputs, output_nodes)
        self.link_stages()

    def display_node_by_id(self, node_id):
        node = next((n for n in self.goods if n.id == node_id), None)
        if not node:
            print(f"❌ Node with ID '{node_id}' not found.")
            return

        print(f"\n🔎 Node Details for ID: {node_id}")
        print("Name:", node.name)
        print("Type:", node.good_type)
        print("Finished:", node.is_finished)
        print("Quantity:", node.quantity, node.unit)

        used_in_stages = []
        as_input_to = []
        for stage in self.stages.values():
            if node in stage.raw_inputs or node in stage.intermediary_inputs:
                used_in_stages.append(stage.number)
            if node in stage.raw_inputs:
                for o in stage.outputs:
                    if node in o.made_from:
                        as_input_to.append(o.name)

        print("Used In Stages:", used_in_stages)
        print("Used As Input To Intermediaries:", as_input_to)

        print("\n🧪 Wastage Details:")
        total_used = 0
        for stage in self.stages.values():
            if node in stage.raw_inputs:
                usage_qty = next((g.quantity for g in stage.raw_inputs if g.name == node.name), 0)
                total_used += usage_qty
                print(f"- Stage {stage.number}: Used {usage_qty} {node.unit}")
                for gid, entry in stage.wastage_entries.items():
                    if gid == node.id:
                        print(f"  ↳ Wastage: {entry['wastage']}{entry['type']}")

        print("\n🔢 Total Usage Across Stages:", total_used, node.unit)
        print("🟢 Defined Quantity in Node:", node.quantity, node.unit)
        if node.quantity:
            percent_used = (total_used / node.quantity) * 100
            print(f"📊 Usage Coverage: {percent_used:.2f}%")

        print("\n🏁 Contributes To Finished Goods:")
        finished_goods = [g for g in self.goods if g.is_finished]
        contributed_to = set()

        def trace_upstream(node, target):
            if node in target.made_from:
                return True
            return any(trace_upstream(node, i) for i in target.made_from)

        for fg in finished_goods:
            if trace_upstream(node, fg):
                contributed_to.add(fg.name)

        if contributed_to:
            for name in contributed_to:
                print(f"  - {name}")
        else:
            print("  None")

    def to_json(self):
        stages = []
        for number, stage in sorted(self.stages.items()):
            stage_data = {
                "stageNumber": number,
                "rawGoods": [
                    {"goodName": g.name, "quantity": g.quantity, "unit": g.unit}
                    for g in stage.raw_inputs
                ],
                "outputGoods": [
                    {"goodName": g.name, "quantity": g.quantity, "unit": g.unit}
                    for g in stage.outputs
                ],
                "productionDetails": {
                    "wastageEntries": [
                        {"goodName": next((n.name for n in self.goods if n.id == gid), None),
                         "wastage": e["wastage"], "wastageType": e["type"]}
                        for gid, e in stage.wastage_entries.items()
                    ],
                    "productionTime": stage.production_time,
                    "outsource": stage.outsource
                }
            }
            stages.append(stage_data)
        return {"productionStages": stages}

    def display_stage_by_number(self, stage_number):
        stage = self.stages.get(stage_number)
        if not stage:
            print(f"❌ Stage {stage_number} not found.")
            return
        print(f"\n🔍 Stage {stage_number} Details")
        print("  ⏱ Time:", stage.production_time)
        print("  🔧 Outsource:", stage.outsource)
        print("  🧪 Wastage:")
        for gid, entry in stage.wastage_entries.items():
            good = next((g for g in self.goods if g.id == gid), None)
            if good:
                print(f"    - {good.name}: {entry['wastage']}{entry['type']}")
        print("  🔹 Raw Inputs:", [g.name for g in stage.raw_inputs])
        print("  🔸 Intermediary Inputs:", [g.name for g in stage.intermediary_inputs])
        print("  🏁 Outputs:", [g.name for g in stage.outputs])

    def display_next_stage_info(self, current_stage_number):
        current_stage = self.stages.get(current_stage_number)
        if current_stage and current_stage.next_stage:
            self.display_stage_by_number(current_stage.next_stage.number)
        else:
            print(f"🔚 No next stage found for Stage {current_stage_number}.")
    def generate_graph_image(self):
        G = nx.DiGraph()
        pos = {}
        labels = {}
        node_colors = []
        stage_annotations = []

        x_gap = 4
        y_base = 0

        for stage_number in sorted(self.stages):
            stage = self.stages[stage_number]
            x_offset = stage_number * x_gap
            y = y_base

            # Annotate stage label
            stage_annotations.append((x_offset + 1, y + 1.5, f"Stage {stage_number}"))

            # Add raw inputs
            for g in sorted(stage.raw_inputs, key=lambda x: x.name):
                G.add_node(g.id)
                pos[g.id] = (x_offset, y)
                labels[g.id] = f"{g.name}\n{g.quantity}{g.unit}"
                node_colors.append("skyblue")
                y -= 1

            # Add intermediary inputs
            for g in sorted(stage.intermediary_inputs, key=lambda x: x.name):
                G.add_node(g.id)
                pos[g.id] = (x_offset + 1, y)
                labels[g.id] = f"{g.name}\n{g.quantity}{g.unit}"
                node_colors.append("lightgreen")
                y -= 1

            # Add outputs
            for g in sorted(stage.outputs, key=lambda x: x.name):
                G.add_node(g.id)
                pos[g.id] = (x_offset + 2, y)
                labels[g.id] = f"{g.name}\n{g.quantity}{g.unit}"
                node_colors.append("orange" if g.is_finished else "gold")
                y -= 1

            # Add edges
            for out in stage.outputs:
                for inp in out.made_from:
                    G.add_edge(inp.id, out.id)

        # Draw graph
        plt.figure(figsize=(16, 8))
        nx.draw(G, pos, with_labels=False, node_size=3000,
                node_color=node_colors, edge_color='gray', arrows=True)
        nx.draw_networkx_labels(G, pos, labels, font_size=8, font_weight="bold")

        # Add stage text labels
        for (x, y, label) in stage_annotations:
            plt.text(x, y, label, fontsize=12, fontweight="bold", ha="center", bbox=dict(facecolor='white', alpha=0.6, edgecolor='gray'))

        plt.title("Production Workflow (Stage-Aware Layout)")
        plt.axis("off")
        plt.tight_layout()
        plt.show()

# -------------------------------
# Example usage
# -------------------------------
if __name__ == "__main__":
    g = ProductionGraph()

    example_json = {
        "productionStages": [
            {
                "stageNumber": 1,
                "rawGoods": [
                    {"goodName": "Wheat", "quantity": 100, "unit": "kg"},
                    {"goodName": "Water", "quantity": 50, "unit": "L"}
                ],
                "productionDetails": {
                    "wastageEntries": [
                        {"goodName": "Wheat", "wastage": 5, "wastageType": "%"}
                    ],
                    "productionTime": "3h 30m",
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
                    {"goodName": "Yeast", "quantity": 2, "unit": "kg"}
                ],
                "productionDetails": {
                    "wastageEntries": [
                        {"goodName": "Dough", "wastage": 2, "wastageType": "%"}
                    ],
                    "productionTime": "2h 0m",
                    "outsource": "No"
                },
                "outputGoods": [
                    {"goodName": "Bread", "quantity": 135, "unit": "kg"}
                ]
            }
        ]
    }

    g.load_from_json(example_json)
    g.display()
    g.generate_graph_image()
    
