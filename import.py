import bpy
import mathutils

import io
from pathlib import Path
import itertools

from struct import unpack

from . import xdb
from . import blob
from . import vertex
from . import skeleton
from . import texture

from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator


class ImportGeometry(Operator, ImportHelper):
    """Load geometry files from Allods Online"""
    bl_idname = "allods.import_geometry"
    bl_label = "Import geometry"

    filter_glob: StringProperty(
        default="*.xdb",
        options={'HIDDEN'},
    )
    lods_load: bpy.props.EnumProperty(
        name="Load LODs",
        description="Which LODs should be loaded",
        items=[
            ("LODALL", "All LODs", ""),
            ("LOD0", "LOD 0", ""),
            ("LOD1", "LOD 1", ""),
            ("LOD2", "LOD 2", "")
        ],
        default="LOD0"
    )

    slots_load: bpy.props.BoolProperty(name="Load bones for slots", default=False)

    def execute(self, context):
        # Load & parsing data
        path = Path(self.filepath)

        parser = xdb.XdbParser(path)
        bin_parser = blob.BinParser(path.with_suffix('.bin'))

        basedir = get_base_dir(path.with_suffix('.bin'), parser.get_binary_file())
        print(f'Resource dir: {basedir}')

        vertex_bin_converters = []
        for vertex_declaration in parser.get_vertex_declarations():
            vertex_bin_converters.append(vertex.VertexBinConverter(vertex_declaration))

        vertex_bin_converter = vertex_bin_converters[0]
        vertex_buffer = bin_parser.get_buffer(parser.get_vertex_buffer())
        vertices = vertex_bin_converter.bin_to_vertices(vertex_buffer)
        index_buffer = bin_parser.get_buffer(parser.get_index_buffer())
        indices = [(unpack('HHH', index_buffer[i*6:i*6+6])) for i in range(len(index_buffer) // 6)]
        skeleton_buffer = bin_parser.get_buffer(parser.get_skeleton())
        skeleton_parser = skeleton.BoneBinParser(skeleton_buffer)
        bones = skeleton_parser.get_bones()
        #print_bones(bones)

        if self.lods_load != "LODALL":
            lods_filter = lambda i: int(self.lods_load[3:4]) == i
        else:
            lods_filter = lambda i: True

        # Create LODs collections
        model_name = str(path.name).split('.')[0]
        collection = bpy.data.collections.new(f"{model_name}")
        bpy.context.scene.collection.children.link(collection)
        lods_collections = {}
        for lod_id in range(min(map(lambda e: len(e.lods), parser.get_model_elements()))):
            if not lods_filter(lod_id):
                continue
            lod_collection = bpy.data.collections.new(f"{model_name}_lod{lod_id}")
            collection.children.link(lod_collection)
            lods_collections[lod_id] = lod_collection

        if len(lods_collections) == 0:
            self.report({"IMPORT ERROR"}, "No LODs to be found. Try to change `Load LODs` param.")
            return {"CANCELLED"}

        # Create model elements
        for model_element in parser.get_model_elements():
            # Load material & texture
            mat = bpy.data.materials.new(name=model_element.material_name)
            mat.blend_method = 'BLEND'
            if len(model_element.material.diffuse_texture) > 0:
                texture_resource = get_resource_path(model_element.material.diffuse_texture, basedir)
                texture_parser = xdb.XdbParser(texture_resource)
                texture_path = get_resource_path(texture_parser.get_binary_file(), basedir).with_suffix('.dds')
                print(f'Loading texture: {texture_path}')
                if not Path.exists(texture_path):
                    texture_data = texture.TextureData(texture_path.with_suffix('.bin'),
                                                    *texture_parser.get_texture_info())
                    texture_data.save_to(texture_path)

                mat.use_nodes = True
                mat.node_tree.nodes.clear()
                mat_output = mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
                principled_node = mat.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
                texture_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
                texture_node.image = bpy.data.images.load(filepath=str(texture_path))
                mat.node_tree.links.new(texture_node.outputs[0], principled_node.inputs[0])
                mat.node_tree.links.new(texture_node.outputs[1], principled_node.inputs[21])
                mat.node_tree.links.new(principled_node.outputs[0], mat_output.inputs[0])

            # Building lods
            for i, lod in enumerate(model_element.lods):
                if not lods_filter(i):
                    continue
                lod_indices = indices[lod.index_buffer_begin//3:lod.index_buffer_end//3]
                lod_vertices = [vertices[i] for i in set(itertools.chain.from_iterable(lod_indices))]
                lod_indices_vertex = [(lod_vertices.index(vertices[i[0]]), lod_vertices.index(vertices[i[1]]), lod_vertices.index((vertices[i[2]]))) for i in lod_indices] 	
                mesh = bpy.data.meshes.new(model_element.name + '_lod' + str(i))
                mesh.from_pydata([v.position for v in lod_vertices], [], lod_indices_vertex)
                mesh.update()
                uv_layer = mesh.uv_layers.new()
                for face in mesh.polygons:
                    for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                        uv_layer.data[loop_idx].uv = lod_vertices[vert_idx].texcoord0
                obj = bpy.data.objects.new(model_element.name + '_lod' + str(i), mesh)
                obj.data.materials.append(mat)
                lods_collections[i].objects.link(obj)
        
        # Create armature
        if len(bones) > 0:
            armature = bpy.data.armatures.new("skeleton")
            armature_obj = bpy.data.objects.new("skeleton", armature)
            collection.objects.link(armature_obj)

            bpy.context.view_layer.objects.active = armature_obj
            bpy.ops.object.mode_set(mode='EDIT')

            bones_obj = {}
            for i, bone in enumerate(bones):
                if not self.slots_load and "Slot" in bone.name:
                    continue

                vector = mathutils.Vector((0.0, 0.0, 0.0, 1.0))
                current_bone = bone
                while current_bone.parent != 65535:
                    vector = vector @ current_bone.local_matrix
                    current_bone = bones[current_bone.parent]

                world = bone.inverted_world_matrix.inverted()

                bone_obj = armature_obj.data.edit_bones.new(bone.name)
                bone_obj.tail = world[3][0:3]
                bones_obj[i] = bone_obj

            for i, bone in enumerate(bones):
                if not self.slots_load and "Slot" in bone.name:
                    continue
                if bone.parent != 65535:
                    bones_obj[i].head = bones_obj[bone.parent].tail
                    bones_obj[i].parent = bones_obj[bone.parent]

            bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}


def print_bones(bones):
    """
        Print pretty graph structure of armature

        NOTE: Using index in array as bone's ID, not `bone.id`
    """
    bones_map = {}

    for i, bone in enumerate(bones):
        children = []
        if i in bones_map:
            children = bones_map[i]['children']

        if bone.parent in bones_map:
            bones_map[bone.parent]['children'].append(i)
        else:
            bones_map[bone.parent] = {'id': bone.parent, 'name': '', 'parent': 65535, 'children': [i]}

        bones_map[i] = {'id': i, 'name': bone.name, 'parent': bone.parent, 'children': children}

    def print_req(id, ind=0):
        print(f"{'-- ' * ind}{(bones_map[id].name if isinstance(bones_map[id], skeleton.Bone) else bones_map[id]['name'])}")
        
        for child in bones_map[id]['children']:
            print_req(child, ind + 1)

    for roots in [i for i in bones_map.keys() if bones_map[i]['parent'] == 65535]:
        print_req(roots)


def get_base_dir(filepath, relative_part):
    relative_part = Path(relative_part)
    return Path(filepath).joinpath(*['..' for _ in range(len(relative_part.parts))]).resolve()

def get_resource_path(resource_path, basedir):
    return Path(basedir) / Path(resource_path)

def menu_func_import(self, context):
    self.layout.operator(ImportGeometry.bl_idname,
                         text="Allods Geometry (.bin)")


def register():
    bpy.utils.register_class(ImportGeometry)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(ImportGeometry)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
