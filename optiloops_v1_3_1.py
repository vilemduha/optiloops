# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

from bpy.props import (
    IntProperty,
    BoolProperty,
    FloatProperty,
)
from math import radians
import bmesh
import bpy
bl_info = {
    "name": "Optiloops",
    "author": "Vilem Duha, 1COD",
    "version": (1, 3, 1),
    "blender": (2, 93, 0),
    "location": "View3D > Mesh > Mesh Tools panel > Optimize loops",
    "description": "Optimize meshes by removing loops with angle threshold",
    "warning": "",
    "wiki_url": "",
    "category": "Add Mesh",
}


def get_loop(self, bm, edge0, sel):

    verts2check = edge0.verts[:]
    checkedverts = []
    loop_edges = [edge0]  # we want this edge twice to detect full loop
    sel.discard(edge0)

    # detection next loop + controls non manifold, to_keep, opened/closed edges
    while verts2check:
        v = verts2check.pop()
        checkedverts.append(v)
        if len(v.link_edges) == 4:
            for e in v.link_edges:
                if e in loop_edges:
                    estart = e

            for e in v.link_edges:
                # any is great
                neighbour = any(f in estart.link_faces for f in e.link_faces)
                if not neighbour:
                    if len(e.link_faces) < 2 or to_keep(self, e, bm):  # non man and keep
                        sel.discard(e)
                        return []  # so "eligible" is False later

                    if self.open_loops_only and e in loop_edges:  # it's a full loop don't dissolve it
                        sel.discard(e)
                        return []

                    else:
                        sel.discard(e)
                        loop_edges.append(e)  # we append the next edge

                        for v in e.verts:  # next vert to check
                            if v not in checkedverts and v not in verts2check:
                                verts2check.append(v)

    if self.only_closed and len(set(loop_edges)) == len(loop_edges):
        return []

    # clean repeated edge and we will use set from there
    loop_edges = list(set(loop_edges))

    return loop_edges


class edgeloop():  # I want to add "holding_edges" attrib to detect borders...
    edges = []  # ...with if previous loop.edges[0] angle >= next edge angle * 2
    neighbours = set()


def check_angles(edges, Min_angle, Max_angle):
    for edge in edges:
        a = edge.calc_face_angle()
        if Max_angle > a > Min_angle:  # I added max angle, why not...
            return False
    return True


def to_keep(self, edge, bm):
    if self.seam and edge.is_valid and edge.seam:
        return True
    if self.bevel:
        bv = bm.edges.layers.bevel_weight.verify()
        # edge.is_valid: to prevent from missing geo when dissolving edges
        if edge.is_valid and edge[bv] > 0:
            return True
    if self.crease:
        cr = bm.edges.layers.crease.verify()
        if edge.is_valid and edge[cr] > 0:
            return True
    return False


def deselect(bm):  # better than ops...
    for v in bm.verts:
        v.select = False
    bm.select_flush(False)


def get_loops(self, bm, sel, Max_angle, Min_angle):

    loops = []
    while sel:
        eligible = True
        last = sel.pop()
        if len(last.link_faces) < 2 or to_keep(self, last, bm):
            eligible = False
            sel.discard(last)
            _loop = []
        else:
            _loop = get_loop(self, bm, last, sel)

        if eligible and len(_loop) < 2:
            eligible = False

        if eligible:
            eligible = check_angles(_loop, Min_angle, Max_angle)

        if eligible:
            loop = edgeloop()  # instanciation
            loop.edges = _loop
            loops.append(loop)

    return loops


def get_neighbours(loops):
    for loop in loops:
        loop.neighbours = set()
        e = loop.edges[0]
        for f in e.link_faces:
            if len(f.verts) == 4:
                for e1 in f.edges:
                    if e1 != e:
                        do = all(v not in e.verts for v in e1.verts)
                        if do:
                            for loop1 in loops:
                                if (
                                    loop1 != loop
                                    and e1 in loop1.edges
                                    and loop1 not in loop.neighbours
                                ):
                                    loop.neighbours.add(loop1)


def skiploop(final_loops, skip_loops, loop):
    final_loops.append(loop)
    last_neighbour = None
    checkneighbours = loop.neighbours
    checked = [loop]
    while checkneighbours:
        neighbour = checkneighbours.pop()
        checked.append(neighbour)
        if neighbour not in checked:
            skip_loops.append(neighbour)

        for n in neighbour.neighbours:
            if n not in checked:
                final_loops.append(n)
                checked.append(n)
                for n1 in n.neighbours:

                    if n1 not in checked:
                        checkneighbours.add(n1)
                        checked.append(n1)
                        skip_loops.append(n1)


def optiloops(self, context):
    cao = bpy.context.active_object
    self.hidden = context.object.name
    bm = bmesh.from_edit_mesh(cao.data)
    bm.normal_update()
    bpy.ops.mesh.select_mode(
        use_extend=False, use_expand=False, type='EDGE')
    Max_angle = radians(self.Max_angle)
    Min_angle = radians(self.Min_angle)
    sel = {e for e in bm.edges if e.select}
    if not sel:
        sel = set(bm.edges[:])

    sel_copy = sel.copy()

    deselect(bm)

    loops = get_loops(self, bm, sel, Max_angle,
                      Min_angle)

    get_neighbours(loops)

    if self.influencing_loops:
        # check for neighbouring loops if they aren't in the cleanup group which means they are where borders start.
        remove_loops = [l for l in loops if len(l.neighbours) < 2]

        for l in remove_loops:
            loops.remove(l)
        get_neighbours(loops)

    if not self.dissolve:
        for l in loops:
            for e in l.edges:
                e.select = True
    else:
        while loops:
            final_loops = []
            skip_loops = []

            for l in loops:
                # if len(l.neighbours) == 1 and next(iter(l.neighbours)) not in final_loops:
                if len(l.neighbours) == 1 and next(iter(l.neighbours)) not in skip_loops and next(iter(l.neighbours)) not in final_loops:
                    skiploop(final_loops, skip_loops, l)

                if len(l.neighbours) == 0:  # only 1 loop exists
                    final_loops.append(l)
            # when mesh seriously dissolved...
            if len(skip_loops) + len(final_loops) < len(loops):
                for l in loops:
                    if l not in skip_loops and l not in final_loops:
                        skiploop(final_loops, skip_loops, l)
                #    if l not in skip_loops and l not in final_loops and nothing was done

            for l in final_loops:
                for e in l.edges:
                    e.select = True
            bpy.ops.mesh.dissolve_edges()
            loops = []
            for l in skip_loops:
                filter = any(e not in bm.edges for e in l.edges)
                if not filter and check_angles(l.edges, Min_angle, Max_angle):
                    loops.append(l)

            get_neighbours(loops)
            # make things iterative here

    # select result geo to make shift+R possible
    if self.sel:
        [e.select_set(True) for e in sel_copy if e in bm.edges]

    bmesh.update_edit_mesh(cao.data)  # missing????


class OPTILOOPS_OT_operator(bpy.types.Operator):
    """Reduces mesh geometry while keeping loops"""
    bl_idname = "mesh.optiloops"
    bl_label = "Optimize loops"
    bl_options = {'REGISTER', 'UNDO'}

    def update_full_loops_only(self, context):
        if self.only_closed:
            self.open_loops_only = False

    def update_open_loops_only(self, context):
        if self.open_loops_only:
            self.only_closed = False

    # Overlay toggle
    def get_overlay_toggle(self):  # (shortcut) to see what the mesh looks like

        return bpy.context.space_data.overlay.show_overlays

    def set_overlay_toggle(self, value):

        bpy.context.space_data.overlay.show_overlays = value

    def update_overlay_toggle(self, context):

        context.space_data.overlay.show_overlays = bool(
            context.scene.overlays_toggle)

    overlays_toggle: bpy.props.BoolProperty(
        get=get_overlay_toggle,
        set=set_overlay_toggle,
        update=update_overlay_toggle
    )
    dissolve: BoolProperty(
        name="DISSOLVE",
        description="If disabled, loops will only be selected",
        default=True,
    )
    sel: BoolProperty(
        name="sel result",
        description="select after dissolve to repeat(Shift+R)",
        default=False,
    )
    Min_angle: FloatProperty(
        name="Min Angle",
        description="lower angles removed",
        min=-0.0001, max=180,
        default=-0.0001,
        precision=1,
        step=1
    )
    Max_angle: FloatProperty(
        name="Max Angle",
        description="Max angles removed",
        min=0.0001, max=180,
        default=180,
        precision=1,
        step=1,
    )
    influencing_loops: BoolProperty(
        name="influencing loops",
        default=False,
    )
    only_closed: BoolProperty(
        name="keep open Loops",
        default=False,
        update=update_full_loops_only,
    )
    open_loops_only: BoolProperty(
        name="Keep closed Loops",
        default=False,
        update=update_open_loops_only,
    )
    seam: BoolProperty(
        name="Keep uv seams",
        description="keep uv seams loops",
        default=False,
    )
    bevel: BoolProperty(
        name="Keep bevel weight",
        description="keep bevel weight loops",
        default=False,
    )
    crease: BoolProperty(
        name="Keep crease weight",
        description="keep crease weight loops",
        default=False,
    )

    hidden_prop: bpy.props.StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        # if new object dissolve False by security on big mesh, if min angle was high
        if self.hidden_prop != context.object.name:
            self.dissolve = False
        return self.execute(context)

    def execute(self, context):
        optiloops(self, context)
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True  # name before for props
        layout.use_property_decorate = False  # reduce margin
        row = layout.row()
        row.label(text="")
        row.prop(self, "overlays_toggle", text="", icon='OVERLAY')
        row = layout.row()
        row.prop(self, "dissolve")
        row.prop(self, "sel")
        layout.prop(self, "Min_angle")
        layout.prop(self, "Max_angle")
        layout.prop(self, "influencing_loops")
        layout.prop(self, "only_closed")
        layout.prop(self, "open_loops_only")
        layout.prop(self, "seam")
        layout.prop(self, "bevel")
        layout.prop(self, "crease")


def optiloops_menu(self, context):
    layout = self.layout
    layout.operator_context = "INVOKE_DEFAULT"
    layout.operator('mesh.optiloops')


def register():
    bpy.utils.register_class(OPTILOOPS_OT_operator)
    bpy.types.VIEW3D_MT_edit_mesh_clean.append(optiloops_menu)
    bpy.types.VIEW3D_MT_edit_mesh_delete.append(optiloops_menu)


def unregister():
    bpy.utils.unregister_class(OPTILOOPS_OT_operator)
    bpy.types.VIEW3D_MT_edit_mesh_clean.remove(optiloops_menu)
    bpy.types.VIEW3D_MT_edit_mesh_delete.remove(optiloops_menu)
