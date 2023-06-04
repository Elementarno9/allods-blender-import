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
        default="LODALL"
    )

    def execute(self, context):
        path = Path(self.filepath)

        parser = xdb.XdbParser(path)
        bin_parser = blob.BinParser(path.with_suffix('.bin'))

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

        if self.lods_load != "LODALL":
            lods_filter = lambda i: int(self.lods_load[3:4]) == i
        else:
            lods_filter = lambda i: True

        model_name = str(path.name).split('.')[0]
        lods_collections = {}
        for lod_id in range(min(map(lambda e: len(e.lods), parser.get_model_elements()))):
            if not lods_filter(lod_id):
                continue
            collection = bpy.data.collections.new(f"{model_name}_lod{lod_id}")
            bpy.context.scene.collection.children.link(collection)
            lods_collections[lod_id] = collection

        if len(lods_collections) == 0:
            self.report({"IMPORT ERROR"}, "No LODs to be found. Try to change `Load LODs` param.")
            return {"CANCELLED"}

        for model_element in parser.get_model_elements():
            # Load material & texture
            mat = bpy.data.materials.new(name=model_element.material_name)
            mat.blend_method = 'BLEND'
            texture_name = Path(model_element.material.diffuse_texture).name
            texture_path = path.with_name(texture_name).with_suffix('.dds')
            if not Path.exists(texture_path):
                texture_parser = xdb.XdbParser(path.with_name(texture_name))
                texture_data = texture.TextureData(path.with_name(Path(texture_parser.get_binary_file()).name),
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
        
        armature = bpy.data.armatures.new("skeleton")
        armature_obj = bpy.data.objects.new("skeleton", armature)
        collection.objects.link(armature_obj)

        bpy.context.view_layer.objects.active = armature_obj

        bpy.ops.object.mode_set(mode='EDIT')

        new_bones = []

        for bone in bones:
            current_bone = bone
            vector = mathutils.Vector((0.0, 0.0, 0.0, 1.0))

            while current_bone.parent != 65535:
                vector = vector @ current_bone.local_matrix
                current_bone = bones[current_bone.parent]

            world = bone.inverted_world_matrix.inverted()

            #o = bpy.data.objects.new( bone.name, None )
            #collection.objects.link(o)
            #o.empty_display_size = 0.01
            #o.empty_display_type = 'PLAIN_AXES'
            #o.location = vector[0:3]

            o = bpy.data.objects.new( bone.name + '_alt', None )
            collection.objects.link(o)
            o.empty_display_size = 0.5
            o.empty_display_type = 'PLAIN_AXES'
            o.location = world[3][0:3]
            o.rotation_euler = world.transposed().to_euler('XYZ')
            new_bones.append(o)

        for index, bone in enumerate(bones):
            d = new_bones[index].location - (new_bones[bone.parent].location if bone.parent != 65535 else mathutils.Vector((0,0,0)))
            axis, roll = bpy.types.Bone.AxisRollFromMatrix(world.transposed().to_3x3(), axis=d)
            print(d, axis, roll)
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(ImportGeometry.bl_idname,
                         text="Allods Geometry (.bin)")


def register():
    bpy.utils.register_class(ImportGeometry)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(ImportGeometry)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
