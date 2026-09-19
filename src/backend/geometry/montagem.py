import math

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.guid
import ifcopenshell.util.shape
import ifcopenshell.validate

from src.backend.geometry.pecas import Extrusao, Revolucao


class Montador:
    def __init__(self, nome, autor="Axio Coder", descricao="", precisao=1e-5, casas=6):
        self.nome = nome
        self.autor = autor
        self.casas = casas
        self.modelo = ifcopenshell.file(schema="IFC4")
        self._contagem = {}
        self._por_nivel = {}
        self._por_material = {}
        self.contexto = self._criar_cabecalho(descricao, precisao)
        self.materiais = {}
        self.projeto = None
        self.terreno = None
        self.edificio = None
        self._criar_arvore_espacial()

    def _criar_arvore_espacial(self):
        modelo = self.modelo
        metro = modelo.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
        area = modelo.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
        volume = modelo.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
        unidades = modelo.create_entity("IfcUnitAssignment", Units=[metro, area, volume])
        self.projeto = modelo.create_entity(
            "IfcProject",
            GlobalId=ifcopenshell.guid.new(),
            Name=self.nome,
            UnitsInContext=unidades,
            RepresentationContexts=[self.contexto],
        )
        self.terreno = modelo.create_entity(
            "IfcSite", GlobalId=ifcopenshell.guid.new(), Name="Implantacao",
            ObjectPlacement=self._colocacao(),
        )
        self.edificio = modelo.create_entity(
            "IfcBuilding", GlobalId=ifcopenshell.guid.new(), Name=self.nome,
            ObjectPlacement=self._colocacao(self.terreno.ObjectPlacement),
        )
        modelo.create_entity(
            "IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
            RelatingObject=self.projeto, RelatedObjects=[self.terreno],
        )
        modelo.create_entity(
            "IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
            RelatingObject=self.terreno, RelatedObjects=[self.edificio],
        )

    def _criar_cabecalho(self, descricao, precisao):
        modelo = self.modelo
        contexto = modelo.create_entity(
            "IfcGeometricRepresentationContext",
            ContextIdentifier="Model",
            ContextType="Model",
            CoordinateSpaceDimension=3,
            Precision=precisao,
            WorldCoordinateSystem=self._colocacao_base(),
        )
        modelo.header.file_name.name = f"{self.nome}.ifc"
        modelo.header.file_name.author = (self.autor,)
        modelo.header.file_name.originating_system = self.autor
        if descricao:
            modelo.header.file_description.description = (descricao,)
        return contexto

    def _colocacao_base(self):
        return self.modelo.create_entity(
            "IfcAxis2Placement3D",
            Location=self.modelo.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=self.modelo.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            RefDirection=self.modelo.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
        )

    def _colocacao(self, relativo=None):
        return self.modelo.create_entity(
            "IfcLocalPlacement", PlacementRelTo=relativo, RelativePlacement=self._colocacao_base()
        )

    def nivel(self, nome, elevacao, descricao=""):
        nivel = self.modelo.create_entity(
            "IfcBuildingStorey",
            GlobalId=ifcopenshell.guid.new(),
            Name=nome,
            Description=descricao or None,
            Elevation=float(elevacao),
            ObjectPlacement=self._colocacao(self.edificio.ObjectPlacement),
        )
        self.modelo.create_entity(
            "IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
            RelatingObject=self.edificio, RelatedObjects=[nivel],
        )
        self._por_nivel.setdefault(nivel, [])
        return nivel

    def material(self, nome, cor, transparencia=0.0, brilho=0.0):
        modelo = self.modelo
        definicao = modelo.create_entity("IfcMaterial", Name=nome)
        superficie = modelo.create_entity(
            "IfcSurfaceStyleRendering",
            SurfaceColour=modelo.create_entity(
                "IfcColourRgb", Name=nome, Red=cor[0], Green=cor[1], Blue=cor[2]
            ),
            Transparency=float(transparencia),
            SpecularColour=modelo.create_entity(
                "IfcColourRgb", Red=brilho, Green=brilho, Blue=brilho
            ),
            ReflectanceMethod="PHONG" if brilho else "NOTDEFINED",
        )
        estilo = modelo.create_entity("IfcSurfaceStyle", Name=nome, Side="BOTH", Styles=[superficie])
        self.materiais[nome] = (definicao, estilo)
        return definicao

    def _chave_material(self, material):
        if material in self.materiais:
            return material
        nome = getattr(material, "Name", None)
        return nome if nome in self.materiais else material

    def peca(self, classe, nome, malhas, nivel, material, descricao="", tipo="", propriedades=None):
        material = self._chave_material(material)
        lista = [malhas] if _e_malha(malhas) else list(malhas)
        representacao = self.modelo.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=self.contexto,
            RepresentationIdentifier="Body",
            RepresentationType="Tessellation",
            Items=[self._malha(vertices, faces, material) for vertices, faces in lista],
        )
        return self._registar(
            classe, nome, representacao, nivel, material, descricao, tipo, propriedades
        )

    def solido(self, peca, nivel, material=None):
        nome_material = self._chave_material(peca.material if material is None else material)
        representacao = self.modelo.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=self.contexto,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[_solido(self.modelo, peca)],
        )
        return self._registar(
            peca.tipo_ifc, peca.nome, representacao, nivel, nome_material,
            peca.descricao, peca.tipo, dict(peca.propriedades) or None,
        )

    def _registar(self, classe, nome, representacao, nivel, material, descricao, tipo, propriedades):
        modelo = self.modelo
        produto = modelo.create_entity(
            classe,
            GlobalId=ifcopenshell.guid.new(),
            Name=nome,
            Description=descricao or None,
            ObjectType=tipo or None,
            ObjectPlacement=self._colocacao(nivel.ObjectPlacement),
            Representation=modelo.create_entity(
                "IfcProductDefinitionShape", Representations=[representacao]
            ),
        )
        self._por_nivel.setdefault(nivel, []).append(produto)
        self._por_material.setdefault(material, []).append(produto)
        self._contagem[classe] = self._contagem.get(classe, 0) + 1
        if propriedades:
            self.propriedades(produto, f"Pset_{nome}", propriedades)
        return produto

    def _malha(self, vertices, faces, material):
        modelo = self.modelo
        casas = self.casas
        pontos = modelo.create_entity(
            "IfcCartesianPointList3D",
            CoordList=[tuple(round(float(c), casas) for c in ponto) for ponto in vertices],
        )
        conjunto = modelo.create_entity(
            "IfcTriangulatedFaceSet",
            Coordinates=pontos,
            Closed=True,
            CoordIndex=[tuple(indice + 1 for indice in face) for face in faces],
        )
        if material in self.materiais:
            modelo.create_entity(
                "IfcStyledItem", Item=conjunto, Styles=[self.materiais[material][1]], Name=material
            )
        return conjunto

    def propriedades(self, produto, nome, valores):
        modelo = self.modelo
        propriedades = []
        for chave, valor in valores.items():
            if isinstance(valor, bool):
                nominal = modelo.create_entity("IfcBoolean", valor)
            elif isinstance(valor, float):
                nominal = modelo.create_entity("IfcReal", valor)
            elif isinstance(valor, int):
                nominal = modelo.create_entity("IfcInteger", valor)
            else:
                nominal = modelo.create_entity("IfcText", str(valor))
            propriedades.append(
                modelo.create_entity("IfcPropertySingleValue", Name=chave, NominalValue=nominal)
            )
        conjunto = modelo.create_entity(
            "IfcPropertySet",
            GlobalId=ifcopenshell.guid.new(),
            Name=nome,
            HasProperties=propriedades,
        )
        modelo.create_entity(
            "IfcRelDefinesByProperties",
            GlobalId=ifcopenshell.guid.new(),
            RelatedObjects=[produto],
            RelatingPropertyDefinition=conjunto,
        )

    def grupo(self, nome, descricao, produtos):
        if not produtos:
            return None
        modelo = self.modelo
        agrupamento = modelo.create_entity(
            "IfcGroup", GlobalId=ifcopenshell.guid.new(), Name=nome, Description=descricao or None
        )
        modelo.create_entity(
            "IfcRelAssignsToGroup",
            GlobalId=ifcopenshell.guid.new(),
            RelatedObjects=list(produtos),
            RelatingGroup=agrupamento,
        )
        return agrupamento

    def documento(self, identificacao, nome, descricao, produtos):
        modelo = self.modelo
        documento = modelo.create_entity(
            "IfcDocumentInformation",
            Identification=identificacao,
            Name=nome,
            Description=descricao or None,
        )
        modelo.create_entity(
            "IfcRelAssociatesDocument",
            GlobalId=ifcopenshell.guid.new(),
            RelatedObjects=list(produtos),
            RelatingDocument=documento,
        )

    def _ligar_conteudos(self):
        for nivel, produtos in self._por_nivel.items():
            if produtos:
                self.modelo.create_entity(
                    "IfcRelContainedInSpatialStructure",
                    GlobalId=ifcopenshell.guid.new(),
                    RelatingStructure=nivel,
                    RelatedElements=produtos,
                )
        for nome, produtos in self._por_material.items():
            if produtos and nome in self.materiais:
                self.modelo.create_entity(
                    "IfcRelAssociatesMaterial",
                    GlobalId=ifcopenshell.guid.new(),
                    Name=f"Material: {nome}",
                    RelatedObjects=produtos,
                    RelatingMaterial=self.materiais[nome][0],
                )

    def contagem(self):
        return dict(sorted(self._contagem.items()))

    def escrever(self, caminho):
        self._ligar_conteudos()
        self.modelo.write(caminho)
        return caminho


def medir(caminho, lista_origem):
    volumes = medir_ifc(caminho)
    medidos = {}
    for produto in lista_origem:
        if produto.Name in volumes:
            medidos[produto.Name] = volumes[produto.Name]
    return medidos


def _e_malha(valor):
    if not isinstance(valor, (tuple, list)) or len(valor) != 2:
        return False
    vertices, faces = valor
    if not isinstance(vertices, (list, tuple)) or not isinstance(faces, (list, tuple)) or not faces:
        return False
    return all(
        isinstance(face, (list, tuple))
        and len(face) >= 3
        and all(isinstance(indice, int) for indice in face)
        for face in faces
    )


def validar(caminho):
    modelo = ifcopenshell.open(caminho)
    registo = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(modelo, registo)
    return [s for s in registo.statements if s.get("level") in ("error", "warning")]
def _normalizar(vetor):
    norma = math.sqrt(sum(componente * componente for componente in vetor))
    if norma < 1e-12:
        return (0.0, 0.0, 1.0)
    return tuple(componente / norma for componente in vetor)
def _placement3d(modelo, origem, eixo_z, eixo_x):
    return modelo.create_entity(
        "IfcAxis2Placement3D",
        Location=modelo.create_entity("IfcCartesianPoint", Coordinates=tuple(float(c) for c in origem)),
        Axis=modelo.create_entity("IfcDirection", DirectionRatios=_normalizar(eixo_z)),
        RefDirection=modelo.create_entity("IfcDirection", DirectionRatios=_normalizar(eixo_x)),
    )
def _perfil(modelo, peca):
    pontos = [
        modelo.create_entity("IfcCartesianPoint", Coordinates=(float(x), float(y)))
        for x, y in peca.perfil.pontos
    ]
    contorno = modelo.create_entity("IfcPolyline", Points=pontos)
    return modelo.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=contorno)
def _solido(modelo, peca):
    perfil = _perfil(modelo, peca)
    posicao = _placement3d(modelo, peca.origem, peca.eixo_z, peca.eixo_x)
    if isinstance(peca.operacao, Extrusao):
        return modelo.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=perfil,
            Position=posicao,
            ExtrudedDirection=modelo.create_entity("IfcDirection", DirectionRatios=peca.operacao.direcao),
            Depth=float(peca.operacao.profundidade),
        )
    if isinstance(peca.operacao, Revolucao):
        eixo = modelo.create_entity(
            "IfcAxis1Placement",
            Location=modelo.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=modelo.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
        )
        return modelo.create_entity(
            "IfcRevolvedAreaSolid",
            SweptArea=perfil,
            Position=posicao,
            Axis=eixo,
            Angle=float(peca.operacao.angulo),
        )
    raise TypeError(f"operacao desconhecida em {peca.nome}: {type(peca.operacao).__name__}")
def medir_ifc(caminho):
    modelo = ifcopenshell.open(caminho)
    definicoes = ifcopenshell.geom.settings()
    iterador = ifcopenshell.geom.iterator(definicoes, modelo)
    volumes = {}
    if not iterador.initialize():
        return volumes
    while True:
        forma = iterador.get()
        volumes[modelo.by_id(forma.id).Name] = ifcopenshell.util.shape.get_volume(forma.geometry)
        if not iterador.next():
            break
    return volumes
