import xml.etree.ElementTree as ET
import distutils.util as du
from . import blob
from . import geometry
from . import vertex

class XdbParser:

    def __init__(self, path):
        self.content = ET.parse(path).getroot()
        self._vertex_declarations = None
        self._index_buffer = None
        self._vertex_buffer = None
        self._model_elements = None
        self._materials = None
        self._skeleton = None
    
    def get_vertex_declarations(self):
        if self._vertex_declarations == None:
            self._vertex_declarations = []
            for item in self.content.findall('vertexDeclarations/Item'):
                position = XdbParser._parse_vertex_component(item.find('position'))
                normal = XdbParser._parse_vertex_component(item.find('normal'))
                color = XdbParser._parse_vertex_component(item.find('color'))
                texcoord0 = XdbParser._parse_vertex_component(item.find('texcoord0'))
                texcoord1 = XdbParser._parse_vertex_component(item.find('texcoord1'))
                weights = XdbParser._parse_vertex_component(item.find('weights'))
                indices = XdbParser._parse_vertex_component(item.find('indices'))
                stride = int(item.find('stride').text)
                self._vertex_declarations.append(vertex.VertexDeclaration(position, normal, color, texcoord0, texcoord1, weights, indices, stride))
        return self._vertex_declarations

    def get_index_buffer(self):
        if self._index_buffer == None:
            localID = int(self.content.find('indexBuffer/localID').text)
            size = int(self.content.find('indexBuffer/size').text)
            self._index_buffer = blob.Blob(localID, size)
        return self._index_buffer

    def get_vertex_buffer(self):
        if self._vertex_buffer == None:
            localID = int(self.content.find('vertexBuffer/localID').text)
            size = int(self.content.find('vertexBuffer/size').text)
            self._vertex_buffer = blob.Blob(localID, size)
        return self._vertex_buffer

    def get_skeleton(self):
        if self._skeleton == None:
            localID = int(self.content.find('skeleton/localID').text)
            size = int(self.content.find('skeleton/size').text)
            self._skeleton = blob.Blob(localID, size)
        return self._skeleton

    def get_model_elements(self):
        if self._model_elements == None:
            self._model_elements = []
            self._materials = {}
            for item in self.content.findall('modelElements/Item'):
                lods = []
                for lod in item.findall('lods/Item'):
                    lods.append(XdbParser._parse_geometry_fragment(lod))
                material = XdbParser._parse_material(item.find('material'))
                material_name = item.find('materialName').text
                name = item.find('name').text
                skin_index = int(item.find('skinIndex').text)
                vertex_buffer_offset = int(item.find('vertexBufferOffset').text)
                vertex_declaration_id = int(item.find('vertexDeclarationID').text)
                virtual_offset = float(item.find('virtualOffset').text)
                self._model_elements.append(geometry.ModelElement(lods, name, material_name, vertex_declaration_id, vertex_buffer_offset, material, skin_index, virtual_offset))
                self._materials[material_name] = material
        return self._model_elements

    def get_binary_file(self):
        return XdbParser._find_href(self.content, 'binaryFile').strip('/')
    
    def get_texture_info(self):
        return (
            int(self.content.find('width').text),
            int(self.content.find('height').text),
            self.content.find('type').text
        )

    @staticmethod
    def _parse_material(xml):
        blend_effect = geometry.BlendEffect[xml.findtext('BlendEffect', default=geometry.BlendEffect.BLEND_EFFECT_ADD)]
        diffuse_texture = XdbParser._find_href(xml, 'diffuseTexture').split('#')[0].strip('/')
        scroll_alpha = bool(du.strtobool(xml.findtext('scrollAlpha', default=True)))
        scroll_rgb = bool(du.strtobool(xml.findtext('ScrollRGB', default=True)))
        transparency_texture = XdbParser._find_href(xml, 'transparencyTexture')
        transparent = bool(du.strtobool(xml.findtext('transparent', default=True)))
        use_fog = bool(du.strtobool(xml.findtext('useFog', default=True)))
        u_translate_speed = float(xml.findtext('uTranslateSpeed', default=0.))
        visible = bool(du.strtobool(xml.findtext('visible', default=True)))
        v_translate_speed = float(xml.findtext('vTranslateSpeed', default=0.))
        return geometry.Material(blend_effect, diffuse_texture, scroll_alpha, scroll_rgb, transparency_texture, transparent, use_fog, u_translate_speed, visible, v_translate_speed)

    @staticmethod
    def _parse_geometry_fragment(xml):
        index_buffer_begin = int(xml.findtext('indexBufferBegin'))
        index_buffer_end = int(xml.findtext('indexBufferEnd'))
        vertex_buffer_begin = int(xml.findtext('vertexBufferBegin'))
        vertex_buffer_end = int(xml.findtext('vertexBufferEnd'))
        return geometry.GeometryFragment(vertex_buffer_begin, vertex_buffer_end, index_buffer_begin, index_buffer_end)

    @staticmethod
    def _parse_vertex_component(xml):
        offset = int(xml.find('offset').text)
        type = vertex.VertexElementType[xml.find('type').text]
        return vertex.VertexComponent(type, offset)

    @staticmethod
    def _find_href(xml, key):
        el = xml.find(key)
        if el == None:
            return None
        else:
            return el.attrib['href']
