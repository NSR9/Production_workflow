from collections import defaultdict

# —————————————————————————————————
# Node classes (unchanged)
# —————————————————————————————————

class RawGoodNode:
    def __init__(self, name):
        self.name = name
        self.good_type = "Raw"
        self.used_in = set()
    def __repr__(self):
        return f"RawGood({self.name})"

class IntermediaryGoodNode:
    def __init__(self, name, stage):
        self.name = name
        self.good_type = "Intermediary"
        self.stage = stage
        self.produced_from = set()
        self.used_in = set()
    def __repr__(self):
        return f"Intermediary({self.name}, stage={self.stage})"

class FinishedGoodNode:
    def __init__(self, name):
        self.name = name
        self.good_type = "Finished"
        self.produced_from = set()
    def __repr__(self):
        return f"Finished({self.name})"

# —————————————————————————————————
# Graph class (unchanged)
# —————————————————————————————————

class ProductionGraph:
    def __init__(self):
        self.nodes = {}   # name → node object
        self.edges = {}   # (source, target) → {quantity, unit}

    def add_good(self, name, node_type, stage=None):
        if name in self.nodes:
            return
        if node_type == "Raw":
            self.nodes[name] = RawGoodNode(name)
        elif node_type == "Intermediary":
            if stage is None:
                raise ValueError("Intermediary goods require a stage")
            self.nodes[name] = IntermediaryGoodNode(name, stage)
        elif node_type == "Finished":
            self.nodes[name] = FinishedGoodNode(name)
        else:
            raise ValueError(f"Unknown node_type: {node_type}")

    def link(self, source, target, quantity=None, unit=None):
        src = self.nodes[source]
        tgt = self.nodes[target]
        if hasattr(src, 'used_in'):
            src.used_in.add(tgt)
        if hasattr(tgt, 'produced_from'):
            tgt.produced_from.add(src)
        self.edges[(source, target)] = {'quantity': quantity, 'unit': unit}

    def display_stage_wise(self):
        raws = sorted(n.name for n in self.nodes.values() if n.good_type=='Raw')
        intermediaries = defaultdict(list)
        for n in self.nodes.values():
            if n.good_type=='Intermediary':
                intermediaries[n.stage].append(n.name)
        finished = sorted(n.name for n in self.nodes.values() if n.good_type=='Finished')

        print("🏭 Raw Goods:")
        for r in raws:
            print("  -", r)

        for stg in sorted(intermediaries):
            print(f"\n🔄 Stage {stg} Intermediaries:")
            for name in sorted(intermediaries[stg]):
                print("  -", name)

        print("\n✅ Finished Goods:")
        for f in finished:
            print("  -", f)

    def display_intermediary_inputs_with_types(graph):
        print("📋 Intermediary Inputs (with types):")
        # sort intermediaries by stage
        intermediaries = sorted(
            (n for n in graph.nodes.values() if n.good_type == "Intermediary"),
            key=lambda x: x.stage
        )
        for node in intermediaries:
            inputs = []
            for src in node.produced_from:
                label = "Raw Good" if src.good_type == "Raw" else "Intermediary Good"
                inputs.append(f"{src.name} ({label})")
            inputs_str = ", ".join(inputs)
            print(f"  - {node.name} (stage {node.stage}) ← {inputs_str}")
    def display_process_up_to_stage(self, max_stage):
        """
        Prints all raw materials and intermediary steps from stage 1 up to max_stage.
        """
        # 1) Collect intermediaries up to that stage
        intermediaries = [
            n for n in self.nodes.values()
            if n.good_type == "Intermediary" and n.stage <= max_stage
        ]

        # 2) From those, find all raw materials they depend on
        raw_inputs = {
            src.name
            for interm in intermediaries
            for src in interm.produced_from
            if src.good_type == "Raw"
        }

        # 3) Display raw materials
        print("🏭 Raw Materials (used up to stage", max_stage, "):")
        for raw in sorted(raw_inputs):
            print("  -", raw)

        # 4) Display intermediaries stage by stage
        print()
        for stage in range(1, max_stage + 1):
            goods_at_stage = [n for n in intermediaries if n.stage == stage]
            if not goods_at_stage:
                continue
            print(f"🔄 Stage {stage} Intermediary Goods:")
            for node in sorted(goods_at_stage, key=lambda x: x.name):
                inputs = []
                for src in sorted(node.produced_from, key=lambda x: x.name):
                    if src.good_type == "Raw":
                        label = "Raw Good"
                    else:
                        label = f"Intermediary Good (stage {src.stage})"
                    inputs.append(f"{src.name} ({label})")
                print("  -", node.name, "←", ", ".join(inputs))
        print()


# —————————————————————————————————
# Example “iron‐weave‐paint‐pack” with custom raw inputs per stage
# —————————————————————————————————

def main():
    g = ProductionGraph()

    # 1) Define all raw materials
    raw_materials = [
        "Steel Rods",       # for frame
        "Iron Sheets",      # another frame input
        "Cotton Fiber",     # for weaving
        "Dye",              # for painting
        "Paint Solvent",    # for painting
        "Cardboard Boxes"   # for packaging
    ]
    for raw in raw_materials:
        g.add_good(raw, "Raw")

    # 2) Define intermediaries (with their stage number)
    intermediaries = [
        ("Iron Frame Prep",  1),
        ("Weaving Yarn",     2),
        ("Painting",         3),
        ("Packaging",        4),
    ]
    for name, stage in intermediaries:
        g.add_good(name, "Intermediary", stage=stage)

    # 3) Define finished product
    g.add_good("Finished Assembly", "Finished")

    # 4) Link each intermediary to its specific raw inputs
    #    (quantities omitted for brevity)
    inputs_map = {
        "Iron Frame Prep": ["Steel Rods", "Iron Sheets"],
        "Weaving Yarn":    ["Cotton Fiber"],
        "Painting":        ["Dye", "Paint Solvent"],
        "Packaging":       ["Cardboard Boxes"]
    }
    for interm, raws in inputs_map.items():
        for raw in raws:
            g.link(raw, interm)

    # 5) Link the intermediary chain
    g.link("Iron Frame Prep", "Weaving Yarn")
    g.link("Weaving Yarn",     "Painting")
    g.link("Painting",         "Packaging")
    g.link("Packaging",        "Finished Assembly")

    # 6) Display everything
    g.display_stage_wise()
    g.display_intermediary_inputs_with_types()
    g.display_process_up_to_stage(3)

if __name__ == "__main__":
    main()
