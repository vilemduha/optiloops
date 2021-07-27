import bmesh
import bpy
from math import radians
from bpy.props import (
    IntProperty,
    BoolProperty,
    FloatProperty,
)
bl_info = {
    "name": "Optiloops",
    "author": "Vilem Duha, reviewed by 1COD",
    "version": (1, 2, 1),
    "blender": (2, 80, 0),
    "location": "View3D > Mesh > Mesh Tools panel > Optimize loops",
    "description": "Optimize meshes by removing loops with angle threshold",
    "warning": "",
    "wiki_url": "",
    "category": "Add Mesh",
}


def deselect(bm):
    for f in bm.edges:
        f.select = False
    for e in bm.edges:
        e.select = False
    for v in bm.verts:
        v.select = False
    bm.select_flush(False)


def get_neighbours(e):
    neighbours = 0
    for f in e.link_faces:
        if len(f.verts) == 4:
            for e1 in f.edges:
                if e1 != e and all(v not in e.verts for v in e1.verts):
                    neighbours += 1
    return neighbours


def check_angles(self, edges, Min_angle_threshold, Max_angle_threshold):
    for e in edges:  # only 1 edge in fact
        if len(e.link_faces) != 2:
            return False
        a = e.calc_face_angle()
        if Min_angle_threshold < a < Max_angle_threshold:
            return False

    return True


def get_loop(self, bm, edge, Min_angle_threshold, Max_angle_threshold):

    try:
        verts2check = edge.verts[:]
    except ReferenceError:
        print("get_loop ReferenceError")
        return []

    checkedverts = []
    loop_edges = [edge]
    not_used = False

    while len(verts2check) > 0:
        v = verts2check.pop()
        checkedverts.append(v)
        if len(v.link_edges) == 4:
            for e in v.link_edges:
                if e in loop_edges:
                    estart = e
                    break
            for e in v.link_edges:
                if all(f not in estart.link_faces for f in e.link_faces):
                    loop_edges.append(e)

                    for v in e.verts:  # next vert to check
                        if v not in checkedverts and v not in verts2check:
                            verts2check.append(v)

    if not check_angles(self, loop_edges, Min_angle_threshold, Max_angle_threshold):
        not_used = True

    if self.keep_seams:  # seam
        for e in loop_edges:
            if e.is_valid and e.seam:
                not_used = loop_edges

    if self.keep_bevel:  # bevel
        bv = bm.edges.layers.bevel_weight.verify()
        for e in loop_edges:
            if e.is_valid and e[bv] > 0:
                not_used = loop_edges

    if self.keep_crease:  # crease
        cr = bm.edges.layers.crease.verify()
        for e in loop_edges:
            if e.is_valid and e[cr] > 0:
                not_used = True

    if self.influencing_loops:
        for e in loop_edges:
            if e and get_neighbours(e) < 2:
                not_used = True

    if not_used:
        return [], loop_edges
    else:
        return loop_edges, []


class OptiloopsOperator(bpy.types.Operator):
    """Reduces mesh geometry while keeping loops"""
    bl_idname = "mesh.optiloops"
    bl_label = "Optimize loops"
    bl_options = {'REGISTER', 'UNDO'}

    def update_wireframe(self, context):

        bpy.ops.view3d.toggle_shading(type='WIREFRAME')

    def update(self, context):
        if self.full_loops_only:
            self.not_full_loops_only = False

    def update1(self, context):
        if self.not_full_loops_only:
            self.full_loops_only = False

    on_selection: BoolProperty(
        name="Wireframe View toggle",
        update=update_wireframe,
        default=False,
    )

    toggle_show_wireframe: BoolProperty(
        name="Wireframe View toggle",
        update=update_wireframe,
        default=False,
    )
    dissolve: BoolProperty(
        name="DISSOLVE",
        description="If disabled, loops will only be selected",
        default=False,
    )
    Min_angle_threshold: FloatProperty(
        name="Min Angle",
        description="lower angles removed",
        min=-0.0001, max=90.0,
        default=-0.0001,
        precision=2,
        step=0.5,
    )
    Max_angle_threshold: FloatProperty(
        name="Max Angle",
        description="Max angles removed",
        min=0.0001, max=90.0,
        default=90,
        precision=2,
        step=1,
    )
    influencing_loops: BoolProperty(
        name="Keep Subsurf modif loops",
        default=False,
    )
    full_loops_only: BoolProperty(
        name="Closed Loops only",
        default=False,
        update=update,
    )
    not_full_loops_only: BoolProperty(
        name="Open Loops only",
        default=False,
        update=update1,
    )
    keep_seams: BoolProperty(
        name="Keep uv seams",
        description="keep uv seams loops",
        default=False,
    )
    keep_bevel: BoolProperty(
        name="Keep bevel weight",
        description="keep bevel weight loops",
        default=False,
    )
    keep_crease: BoolProperty(
        name="Keep crease weight",
        description="keep crease weight loops",
        default=False,

    )

    def execute(self, context):

        cao = bpy.context.active_object
        bm = bmesh.from_edit_mesh(cao.data)

        bm.normal_update()
        bm.verts.ensure_lookup_table()
        sel = {e for e in bm.edges if e.select}
        if not sel:
            self.report({'ERROR'}, "Select some geometry first")
            return {'CANCELLED'}

        sel_copy = sel.copy()
        deselect(bm)

        Max_angle_threshold = radians(self.Max_angle_threshold)
        Min_angle_threshold = radians(self.Min_angle_threshold)

        bpy.ops.mesh.select_mode(
            use_extend=False, use_expand=False, type='EDGE')

        loops = []
        while sel_copy:
            last = sel_copy.pop()
            loop, not_used = get_loop(self, bm, last, Min_angle_threshold,
                                      Max_angle_threshold)

            if not_used:
                for e in not_used:
                    sel_copy.discard(e)
                continue

            if self.full_loops_only:
                if len(loop) > len(set(loop)):
                    loops.append(set(loop))
            elif self.not_full_loops_only:
                if len(loop) == len(set(loop)):
                    loops.append(set(loop))
            else:
                loops.append(set(loop))

            for e in loop:
                sel_copy.discard(e)

        if self.dissolve:
            edges = []

            for loop in loops:
                for e in loop:
                    try:
                        if e not in edges: #to avoid a value error with the bmesh operator below
                            edges.append(e)
                    except ReferenceError:
                        continue

            bmesh.ops.dissolve_edges(bm, edges=edges, use_verts=True) #seems ok
            # bpy.ops.mesh.dissolve_mode(use_verts=True)  

        else:
            for loop in loops:
                for e in loop:
                    try:
                        e.select = True
                    except ReferenceError:
                        continue

        bmesh.update_edit_mesh(cao.data)
        return {'FINISHED'}


def optiloops_menu(self, context):
    layout = self.layout
    layout.operator('mesh.optiloops')


def register():
    bpy.utils.register_class(OptiloopsOperator)
    bpy.types.VIEW3D_MT_edit_mesh_clean.append(optiloops_menu)
    bpy.types.VIEW3D_MT_edit_mesh_delete.append(optiloops_menu)


def unregister():
    bpy.utils.unregister_class(OptiloopsOperator)
    bpy.types.VIEW3D_MT_edit_mesh_clean.remove(optiloops_menu)
    bpy.types.VIEW3D_MT_edit_mesh_delete.remove(optiloops_menu)
