import bpy
import numpy as np
from ..base.object import ObjectGN
from ..utils.butils import object_mode, compareNodeType
from ..utils.utils_node import get_node_by_name
from ..utils import number2String, string2Number
import logging

# logger = logging.getLogger('batoms')
logger = logging.getLogger(__name__)

default_attributes = [
    {"name": "atoms_index", "data_type": "INT"},
    {"name": "species_index", "data_type": "INT"},
    {"name": "show", "data_type": "INT"},
    {"name": "select", "data_type": "INT"},
    {"name": "model_style", "data_type": "INT"},
    {"name": "scale", "data_type": "FLOAT"},
]

default_GroupInput = [
    ["atoms_index", "NodeSocketInt"],
    ["species_index", "NodeSocketInt"],
    ["show", "NodeSocketBool"],
    ["select", "NodeSocketInt"],
    ["model_style", "NodeSocketInt"],
    ["scale", "NodeSocketFloat"],
]


default_search_bond_datas = {
    "atoms_index": np.ones(0, dtype=int),
    "species_index": np.ones(0, dtype=int),
    "species": np.ones(0, dtype="U4"),
    "positions": np.zeros((0, 3)),
    "scales": np.zeros(0),
    "offsets": np.zeros((0, 3)),
    "model_styles": np.ones(0, dtype=int),
    "shows": np.ones(0, dtype=int),
    "selects": np.ones(0, dtype=int),
}


class SearchBond(ObjectGN):
    def __init__(
        self,
        label=None,
        search_bond_datas=None,
        batoms=None,
        load=False,
    ):
        """SearchBond Class

        Args:
            label (_type_, optional): _description_. Defaults to None.
            search_bond_datas (_type_, optional): _description_. Defaults to None.
            batoms (_type_, optional): _description_. Defaults to None.
        """
        #
        self.batoms = batoms
        self.label = label
        name = "search_bond"
        ObjectGN.__init__(self, label, name)
        if not load or not self.loadable():
            if search_bond_datas is not None:
                self.build_object(search_bond_datas)
            else:
                self.build_object(default_search_bond_datas)

    def loadable(self):
        """Check loadable or not"""
        # object exist
        obj = bpy.data.objects.get(self.obj_name)
        if obj is None:
            return False
        # batoms exist, and flag is True
        # coll = bpy.data.collections.get(self.label)
        # if coll is None:
        # return False
        # return coll.Bbond.flag
        return True

    def build_object(self, datas, attributes={}):
        """
        build child object and add it to main objects.
        """
        # tstart = time()
        if len(datas["positions"].shape) == 2:
            self.trajectory = {
                "positions": np.array([datas["positions"]]),
                "offsets": np.array([datas["offsets"]]),
            }
            positions = datas["positions"]
            offsets = datas["offsets"]
        elif len(datas["positions"].shape) == 3:
            self.trajectory = {
                "positions": datas["positions"],
                "offsets": datas["offsets"],
            }
            positions = datas["positions"][0]
            offsets = datas["offsets"][0]
        else:
            raise Exception("Shape of positions is wrong!")
        #
        attributes.update(
            {
                "atoms_index": datas["atoms_index"],
                "species_index": datas["species_index"],
                "show": datas["shows"],
                "model_style": datas["model_styles"],
                "select": datas["selects"],
                "scale": datas["scales"],
            }
        )
        name = "%s_search_bond" % self.label
        self.delete_obj(name)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(positions, [], [])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        # Add attributes
        for att in default_attributes:
            self.add_attribute(**att)
        self.batoms.coll.objects.link(obj)
        obj.batoms.type = "BOND"
        obj.batoms.label = self.batoms.label
        obj.Bbond.label = self.batoms.label
        obj.parent = self.batoms.obj
        #
        name = "%s_search_bond_offset" % self.label
        self.delete_obj(name)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(offsets, [], [])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        self.batoms.coll.objects.link(obj)
        obj.hide_set(True)
        obj.parent = self.obj
        bpy.context.view_layer.update()
        self.set_attributes(attributes)
        self.init_geometry_node_modifier(default_GroupInput)
        self.build_geometry_node()
        self.set_trajectory(self.trajectory)
        # print('boundary: build_object: {0:10.2f} s'.format(time() - tstart))

    def update(self, bondlist, mollists, moldatas, arrays, cell):
        self.hide = False
        search_bond_data = self.calc_search_bond_data(
            bondlist, mollists, moldatas, arrays, cell
        )
        self.set_arrays(search_bond_data)

    def build_geometry_node(self):
        """ """
        from ..utils.utils_node import get_projected_position

        nodes = self.gn_node_group.nodes
        links = self.gn_node_group.links
        GroupInput = nodes[0]
        GroupOutput = nodes[1]
        # ------------------------------------------------------------------
        JoinGeometry = get_node_by_name(
            nodes, "%s_JoinGeometry" % self.label, "GeometryNodeJoinGeometry"
        )
        links.new(GroupInput.outputs["Geometry"], JoinGeometry.inputs["Geometry"])
        links.new(JoinGeometry.outputs["Geometry"], GroupOutput.inputs["Geometry"])
        # ------------------------------------------------------------------
        # transform postions of batoms to boundary
        ObjectBatoms = get_node_by_name(
            nodes, "%s_ObjectBatoms" % self.label, "GeometryNodeObjectInfo"
        )
        ObjectBatoms.inputs["Object"].default_value = self.batoms.obj
        PositionBatoms = get_node_by_name(
            nodes, "%s_PositionBatoms" % (self.label), "GeometryNodeInputPosition"
        )
        TransferBatoms = get_node_by_name(
            nodes, "%s_TransferBatoms" % (self.label), "GeometryNodeSampleIndex"
        )
        TransferBatoms.data_type = "FLOAT_VECTOR"
        links.new(ObjectBatoms.outputs["Geometry"], TransferBatoms.inputs[0])
        links.new(PositionBatoms.outputs["Position"], TransferBatoms.inputs[1])
        links.new(GroupInput.outputs[1], TransferBatoms.inputs["Index"])
        # ------------------------------------------------------------------
        # add positions with offsets
        # transfer offsets from object self.obj_o
        ObjectOffsets = get_node_by_name(
            nodes, "%s_ObjectOffsets" % (self.label), "GeometryNodeObjectInfo"
        )
        ObjectOffsets.inputs["Object"].default_value = self.obj_o
        PositionOffsets = get_node_by_name(
            nodes, "%s_PositionOffsets" % (self.label), "GeometryNodeInputPosition"
        )
        IndexOffsets = get_node_by_name(
            nodes, "%s_IndexOffsets" % (self.label), "GeometryNodeInputIndex"
        )
        TransferOffsets = get_node_by_name(
            nodes, "%s_TransferOffsets" % self.label, "GeometryNodeSampleIndex"
        )
        TransferOffsets.data_type = "FLOAT_VECTOR"
        links.new(ObjectOffsets.outputs["Geometry"], TransferOffsets.inputs[0])
        links.new(PositionOffsets.outputs["Position"], TransferOffsets.inputs[1])
        links.new(IndexOffsets.outputs["Index"], TransferOffsets.inputs[2])
        # get cartesian positions
        project_point = get_projected_position(
            self.gn_node_group,
            TransferOffsets.outputs["Value"],
            self.batoms.cell.obj,
            self.label,
            scaled=False,
        )
        # we need one add operation to get the positions with offset
        VectorAdd = get_node_by_name(
            nodes, "%s_VectorAdd" % (self.label), "ShaderNodeVectorMath"
        )
        VectorAdd.operation = "ADD"
        links.new(TransferBatoms.outputs["Value"], VectorAdd.inputs[0])
        links.new(project_point.outputs[0], VectorAdd.inputs[1])
        # set positions
        SetPosition = get_node_by_name(
            nodes, "%s_SetPosition" % self.label, "GeometryNodeSetPosition"
        )
        links.new(GroupInput.outputs["Geometry"], SetPosition.inputs["Geometry"])
        links.new(VectorAdd.outputs[0], SetPosition.inputs["Position"])
        #
        # ------------------------------------------------------------------
        # transform scale of batoms to boundary
        if bpy.app.version_string >= "3.2.0":
            ScaleBatoms = get_node_by_name(
                nodes,
                "%s_ScaleBatoms" % (self.label),
                "GeometryNodeInputNamedAttribute",
            )
            # need to be "FLOAT_VECTOR", because scale is "FLOAT_VECTOR"
            ScaleBatoms.data_type = "FLOAT_VECTOR"
            ScaleBatoms.inputs[0].default_value = "scale"
            TransferScale = get_node_by_name(
                nodes, "%s_TransferScale" % (self.label), "GeometryNodeSampleIndex"
            )
            TransferScale.data_type = "FLOAT_VECTOR"
            links.new(ObjectBatoms.outputs["Geometry"], TransferScale.inputs[0])
            links.new(ScaleBatoms.outputs["Attribute"], TransferScale.inputs[1])
            links.new(GroupInput.outputs[1], TransferScale.inputs["Index"])

    def add_geometry_node(self, spname):
        """ """
        nodes = self.gn_node_group.nodes
        links = self.gn_node_group.links
        GroupInput = nodes[0]
        SetPosition = get_node_by_name(nodes, "%s_SetPosition" % self.label)
        JoinGeometry = get_node_by_name(
            nodes, "%s_JoinGeometry" % self.label, "GeometryNodeJoinGeometry"
        )
        CompareSpecies = get_node_by_name(
            nodes, "CompareFloats_%s_%s" % (self.label, spname), compareNodeType
        )
        CompareSpecies.operation = "EQUAL"
        # CompareSpecies.data_type = 'INT'
        CompareSpecies.inputs[1].default_value = string2Number(spname)
        InstanceOnPoint = get_node_by_name(
            nodes,
            "InstanceOnPoint_%s_%s" % (self.label, spname),
            "GeometryNodeInstanceOnPoints",
        )
        ObjectInfo = get_node_by_name(
            nodes, "ObjectInfo_%s_%s" % (self.label, spname), "GeometryNodeObjectInfo"
        )
        ObjectInfo.inputs["Object"].default_value = self.batoms.species.instancers[
            spname
        ]
        BoolShow = get_node_by_name(
            nodes,
            "BooleanMath_%s_%s_1" % (self.label, spname),
            "FunctionNodeBooleanMath",
        )
        #
        links.new(SetPosition.outputs["Geometry"], InstanceOnPoint.inputs["Points"])
        links.new(GroupInput.outputs[2], CompareSpecies.inputs[0])
        links.new(GroupInput.outputs[3], BoolShow.inputs[0])
        # transfer scale
        if bpy.app.version_string >= "3.2.0":
            TransferScale = get_node_by_name(
                nodes, "%s_TransferScale" % (self.label), "GeometryNodeSampleIndex"
            )
            links.new(TransferScale.outputs["Value"], InstanceOnPoint.inputs["Scale"])
        else:
            links.new(GroupInput.outputs[6], InstanceOnPoint.inputs["Scale"])
        links.new(CompareSpecies.outputs[0], BoolShow.inputs[1])
        links.new(BoolShow.outputs["Boolean"], InstanceOnPoint.inputs["Selection"])
        links.new(ObjectInfo.outputs["Geometry"], InstanceOnPoint.inputs["Instance"])
        links.new(InstanceOnPoint.outputs["Instances"], JoinGeometry.inputs["Geometry"])

    def update_geometry_node_instancer(self, spname, instancer):
        """When instances are re-build, we need also update
        the geometry node.

        Args:
            spname (str): name of the species
        """
        from ..utils.utils_node import get_node_by_name

        # update  instancers
        ObjectInfo = get_node_by_name(
            self.gn_node_group.nodes,
            "ObjectInfo_%s_%s" % (self.label, spname),
            "GeometryNodeObjectInfo",
        )
        ObjectInfo.inputs["Object"].default_value = instancer
        logger.debug("update boundary instancer: {}".format(spname))

    @property
    def obj_o(self):
        return self.get_obj_o()

    def get_obj_o(self):
        name = "%s_search_bond_offset" % self.label
        obj_o = bpy.data.objects.get(name)
        if obj_o is None:
            raise KeyError("%s object is not exist." % name)
        return obj_o

    def get_search_bond(self):
        boundary = np.array(self.batoms.obj.batoms.boundary)
        return boundary.reshape(3, -1)

    def set_arrays(self, arrays):
        """ """
        attributes = self.attributes
        # same length
        dnvert = len(arrays["species_index"]) - len(attributes["species_index"])
        if dnvert > 0:
            self.add_vertices_bmesh(dnvert)
            self.add_vertices_bmesh(dnvert, self.obj_o)
        elif dnvert < 0:
            self.delete_vertices_bmesh(range(-dnvert))
            self.delete_vertices_bmesh(range(-dnvert), self.obj_o)
        if len(self) == 0:
            self.update_mesh()
            return
        self.positions = arrays["positions"][0]
        self.offsets = arrays["offsets"][0]
        self.set_trajectory(arrays)
        species_index = [string2Number(sp) for sp in arrays["species"]]
        self.set_attributes(
            {
                "atoms_index": arrays["atoms_index"],
                "species_index": species_index,
                "scale": arrays["scales"],
                "show": arrays["shows"],
            }
        )
        species = np.unique(arrays["species"])
        for sp in species:
            self.add_geometry_node(sp)

    def get_arrays(self):
        """ """
        object_mode()
        # tstart = time()
        arrays = self.attributes
        arrays.update({"positions": self.positions})
        arrays.update({"offsets": self.offsets})
        # radius
        radius = self.batoms.radius
        arrays.update({"radius": np.zeros(len(self))})
        species = np.array(
            [number2String(i) for i in arrays["species_index"]], dtype="U20"
        )
        arrays["species"] = species
        for sp, value in radius.items():
            mask = np.where(arrays["species"] == sp)
            arrays["radius"][mask] = value
        # size
        arrays["size"] = arrays["radius"] * arrays["scale"]
        # main elements
        main_elements = self.batoms.species.main_elements
        elements = [main_elements[sp] for sp in arrays["species"]]
        arrays.update({"elements": np.array(elements, dtype="U20")})
        # print('get_arrays: %s'%(time() - tstart))
        return arrays

    @property
    def search_bond_data(self):
        return self.get_search_bond_data()

    def get_search_bond_data(self, include_batoms=False):
        """
        using foreach_get and foreach_set to improve performance.
        """
        arrays = self.arrays
        search_bond_data = {
            "positions": arrays["positions"],
            "species": arrays["species"],
            "indices": arrays["atoms_index"],
            "offsets": arrays["offsets"],
        }
        return search_bond_data

    @property
    def offsets(self):
        return self.get_offsets()

    def get_offsets(self):
        """
        using foreach_get and foreach_set to improve performance.
        """
        n = len(self)
        offsets = np.empty(n * 3, dtype=int)
        self.obj_o.data.vertices.foreach_get("co", offsets)
        return offsets.reshape((n, 3))

    @offsets.setter
    def offsets(self, offsets):
        self.set_offsets(offsets)

    def set_offsets(self, offsets):
        """
        Set global offsets to local vertices
        """
        object_mode()
        n = len(self.obj_o.data.vertices)
        if len(offsets) != n:
            raise ValueError("offsets has wrong shape %s != %s." % (len(offsets), n))
        if n == 0:
            return
        offsets = offsets.reshape((n * 3, 1))
        if self.obj_o.data.shape_keys is None and len(self) > 0:
            base_name = "Basis_%s" % self.obj_o.name
            self.obj_o.shape_key_add(name=base_name)
        self.obj_o.data.shape_keys.key_blocks[0].data.foreach_set("co", offsets)
        self.obj_o.data.update()
        self.update_mesh(self.obj_o)

    @property
    def bondlists(self):
        return self.get_bondlists()

    def get_bondlists(self):
        bondlists = self.batoms.bond.arrays
        return bondlists

    def get_trajectory(self):
        """ """
        trajectory = {}
        trajectory["positions"] = self.get_obj_trajectory(self.obj)
        trajectory["offsets"] = self.get_obj_trajectory(self.obj_o)
        return trajectory

    def set_trajectory(self, trajectory=None, frame_start=0):
        if trajectory is None:
            trajectory = self.trajectory
        nframe = len(trajectory)
        if nframe == 0:
            return
        name = "%s_search_bond" % (self.label)
        obj = self.obj
        self.set_shape_key(name, obj, trajectory["positions"], frame_start=frame_start)
        #
        name = "%s_search_bond_offset" % (self.label)
        obj = self.obj_o
        self.set_shape_key(name, obj, trajectory["offsets"], frame_start=frame_start)

    def calc_search_bond_data(self, bondlists, mollists, moldatas, arrays, cell):
        """ """
        # tstart = time()
        # 9th column of bondlists is search bond type 1
        # search type 1: atoms search by bond, the one with offset
        indices1 = np.where((bondlists[:, 2:5] != np.array([0, 0, 0])).any(axis=1))[0]
        indices2 = np.where((bondlists[:, 5:8] != np.array([0, 0, 0])).any(axis=1))[0]
        n = len(indices1) + len(indices2)
        if n == 0:
            return default_search_bond_datas
        bondlists1 = bondlists[indices1]
        bondlists1 = bondlists1[:, [0, 2, 3, 4]]
        bondlists1 = np.unique(bondlists1, axis=0)
        indices1 = bondlists1[:, 0].astype(int)
        model_styles1 = arrays["model_style"][indices1]
        shows1 = arrays["show"][indices1]
        selects1 = arrays["select"][indices1]
        scales1 = arrays["scale"][indices1]
        species_indexs1 = arrays["species_index"][indices1]
        species1 = arrays["species"][indices1]
        offset_vectors1 = bondlists1[:, 1:4]
        positions1 = arrays["positions"][indices1] + np.dot(offset_vectors1, cell)
        # ------------------------------------
        #
        bondlists2 = bondlists[indices2]
        bondlists2 = bondlists2[:, [1, 5, 6, 7]]
        bondlists2 = np.unique(bondlists2, axis=0)
        indices2 = bondlists2[:, 0].astype(int)
        model_styles2 = arrays["model_style"][indices2]
        shows2 = arrays["show"][indices2]
        selects2 = arrays["select"][indices2]
        scales2 = arrays["scale"][indices2]
        species_indexs2 = arrays["species_index"][indices2]
        species2 = arrays["species"][indices2]
        offset_vectors2 = bondlists2[:, 1:4]
        positions2 = arrays["positions"][indices2] + np.dot(offset_vectors2, cell)
        #
        indices = np.append(indices1, indices2)
        species_indexs = np.append(species_indexs1, species_indexs2)
        species = np.append(species1, species2)
        positions = np.append(positions1, positions2, axis=0)
        offset_vectors = np.append(offset_vectors1, offset_vectors2, axis=0)
        model_styles = np.append(model_styles1, model_styles2)
        selects = np.append(selects1, selects2)
        shows = np.append(shows1, shows2)
        scales = np.append(scales1, scales2)
        datas = {
            "atoms_index": np.array(indices),
            "species_index": species_indexs,
            "species": species,
            "positions": np.array([positions]),
            # 'offsets':offsets,
            "offsets": np.array([offset_vectors]),
            "model_styles": model_styles,
            "shows": shows,
            "selects": selects,
            "scales": scales,
        }
        # =========================
        # # search molecule
        # atoms_index = []
        # for b in mollists:
        #     indices = moldatas[b[0]]
        #     datas['atoms_index'] = np.append(datas['atoms_index'], indices)
        #     datas['offsets'] = np.append(datas['offsets'], b[5:8])

        # print('datas: ', datas)
        # print('calc_search_bond_data: {0:10.2f} s'.format(time() - tstart))
        return datas
