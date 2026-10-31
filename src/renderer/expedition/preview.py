"""Immutable previews and the existing Expedition sprite/camera presentation.

A preview contains initial drawing facts only. It is never a Recording/Frame.
"""
from dataclasses import dataclass
from .assets import CELL, SpriteBank
from .camera import Camera
from .model import Entity
from .view import ExpeditionViewer, BG, PANEL, INK, MUTED


@dataclass(frozen=True, slots=True)
class MapScene:
    terrain: tuple[str, ...]
    start: tuple[int, int] | None = None
    exit: tuple[int, int] | None = None
    position: tuple[int, int] | None = None
    artifacts: tuple[Entity, ...] = ()
    enemies: tuple[Entity, ...] = ()
    visited: tuple[tuple[int, int], ...] = ()
    pose: str = 'idle'
    direction: str = 'south'
    completed: bool = False


@dataclass(frozen=True, slots=True)
class WorldPreview:
    scene: MapScene

    @classmethod
    def from_level(cls, level):
        cell=lambda p:(p.row,p.column)
        patrols={p.enemy_id:p for p in level.patrols}
        enemies=[]
        for enemy in level.enemies:
            patrol=patrols.get(enemy.enemy_id)
            position=enemy.position if patrol is None else patrol.positions[patrol.initial_phase]
            enemies.append(Entity(enemy.enemy_id,cell(position),enemy.encounter_penalty,
                                  patrol is not None,None if patrol is None else patrol.initial_phase))
        return cls(MapScene(level.terrain.terrain_rows,cell(level.start),cell(level.exit),cell(level.start),
            tuple(Entity(a.artifact_id,cell(a.position),a.value) for a in level.artifacts),tuple(enemies)))


@dataclass(frozen=True, slots=True)
class TerrainPreview:
    scene: MapScene

    @classmethod
    def from_terrain(cls, terrain): return cls(MapScene(terrain.terrain_rows))


def recorded_scene(recording, frame):
    return MapScene(recording.terrain,recording.start,recording.exit,frame.position,frame.artifacts,
        frame.enemies,frame.visited,frame.pose,frame.direction,frame.completed)


class WorkbenchCamera(Camera):
    @property
    def fit_scale(self): return min(4.0,super().fit_scale)


class PreviewBoard:
    # Reuse the shipped sprite path, including cache bounds and fallbacks.
    _sprite=ExpeditionViewer._sprite

    def __init__(self,parent,tk,fonts,manifest,*,scale=1.0,on_inspect=None):
        self.tk,self.fonts,self.ui_scale=tk,fonts,scale
        self.canvas=tk.Canvas(parent,bg=BG,highlightthickness=1,highlightbackground='#c5cdc4',
                              highlightcolor='#206b66',takefocus=True,cursor='hand2',width=1,height=1)
        self.bank=SpriteBank(tk,parent.winfo_toplevel(),manifest)
        self.camera=WorkbenchCamera(1,1,margin=self.dp(36))
        self.scene=None;self.frame_photos=[];self.drag_point=None;self.on_inspect=on_inspect
        self.canvas.bind('<Configure>',self.resize)
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<ButtonPress-1>',self.press)
        self.canvas.bind('<B1-Motion>',self.drag)
        self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<KeyPress>',self.key)

    def dp(self,value): return max(1,round(value*self.ui_scale))

    def set_scene(self,scene):
        if not isinstance(scene,MapScene): raise TypeError('MAP_SCENE_REQUIRED')
        if self.scene is None or self.scene.terrain!=scene.terrain:
            self.camera=WorkbenchCamera(len(scene.terrain),len(scene.terrain[0]),margin=self.dp(36))
            self.camera.resize(max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height()))
        self.scene=scene;self.draw()

    def resize(self,event):
        self.camera.resize(max(1,event.width),max(1,event.height));self.draw()

    def fit(self): self.camera.fit();self.draw()
    def zoom(self,factor,x=None,y=None): self.camera.zoom(factor,x,y);self.draw()
    def wheel(self,event): self.zoom(1.25**max(-3,min(3,event.delta/120)),event.x,event.y);return 'break'

    def press(self,event):
        self.canvas.focus_set();self.drag_point=(event.x,event.y);self.press_point=self.drag_point
        return 'break'

    def drag(self,event):
        if self.drag_point is not None:
            x,y=self.drag_point;self.camera.pan(event.x-x,event.y-y);self.drag_point=(event.x,event.y);self.draw()
        return 'break'

    def release(self,event):
        if self.drag_point is not None and self.on_inspect is not None and self.scene is not None:
            if abs(event.x-self.press_point[0])+abs(event.y-self.press_point[1])<5:
                x,y=self.camera.world_at(event.x,event.y);cell=(int(y//CELL),int(x//CELL))
                lines=[]
                for entity in self.scene.artifacts:
                    if entity.position==cell: lines.append(f'Artifact {entity.entity_id}: value {entity.value}; row {cell[0]}, column {cell[1]}.')
                for entity in self.scene.enemies:
                    if entity.position==cell: lines.append(f'{"Patrol" if entity.patrol else "Static enemy"} {entity.entity_id}: encounter cost {entity.value}; row {cell[0]}, column {cell[1]}.')
                if lines:self.on_inspect(' '.join(lines))
        self.drag_point=None;return 'break'

    def key(self,event):
        moves={'Left':(40,0),'Right':(-40,0),'Up':(0,40),'Down':(0,-40)}
        if event.keysym in moves:self.camera.pan(*moves[event.keysym]);self.draw()
        elif event.keysym in ('plus','equal','KP_Add'):self.zoom(1.25)
        elif event.keysym in ('minus','KP_Subtract'):self.zoom(.8)
        elif event.keysym in ('f','F','Home'):self.fit()
        else:return None
        return 'break'

    def label(self,text,x,y):
        c=self.canvas
        item=c.create_text(x,y,text=text,font=self.fonts['small'],fill=INK,anchor='n')
        box=c.bbox(item)
        if box is None:return
        shift=max(3-box[0],min(0,self.camera.width-3-box[2]))
        if shift:c.move(item,shift,0);box=c.bbox(item)
        if box[3]>self.camera.height-2:
            c.move(item,0,-(box[3]-self.camera.height+3));box=c.bbox(item)
        backing=c.create_rectangle(box[0]-2,box[1]-1,box[2]+2,box[3]+1,fill=PANEL,outline='')
        c.tag_lower(backing,item)

    def draw(self):
        if self.scene is None:return
        scene,c,camera=self.scene,self.canvas,self.camera
        c.delete('all');self.frame_photos=[]
        rows,columns=camera.visible();size=CELL*camera.scale
        for row in rows:
            for col in columns:self._sprite('floor' if scene.terrain[row][col]=='.' else 'wall',(row,col))
        for position in scene.visited:
            if position[0] in rows and position[1] in columns:
                x,y,x2,y2=camera.box(*position)
                c.create_rectangle(x+2,y+2,x2-2,y2-2,fill='#dce9df',outline='')
        if scene.start is not None:self._sprite('start',scene.start)
        if scene.exit is not None:self._sprite('exit',scene.exit,'accepted' if scene.completed else 'available')
        for artifact in scene.artifacts:self._sprite('artifact',artifact.position)
        for enemy in scene.enemies:
            self._sprite('enemy',enemy.position,direction=enemy.direction)
            if enemy.patrol and size>=24:
                x,y,x2,y2=camera.box(*enemy.position)
                c.create_oval(x+2,y+2,x2-2,y2-2,outline='#684577',width=2,dash=(4,3))
                c.create_text(x2-3,y+3,text='P',anchor='ne',font=self.fonts['small'],fill='#684577')
        if scene.position is not None:self._sprite('explorer',scene.position,scene.pose,scene.direction)
        if size>=28:
            for position,text in ((scene.start,'Start'),(scene.exit,'Exit accepted' if scene.completed else 'Exit')):
                if position is not None and position[0] in rows and position[1] in columns:
                    x,y,x2,y2=camera.box(*position);self.label(text,(x+x2)/2,y2+self.dp(3))
            for row in rows:
                x,y,x2,y2=camera.box(row,0)
                c.create_text(max(self.dp(12),x-self.dp(10)),(y+y2)/2,text=str(row),anchor='e',font=self.fonts['small'],fill=MUTED)
            for col in columns:
                x,y,x2,y2=camera.box(0,col)
                c.create_text((x+x2)/2,max(self.dp(16),y-self.dp(12)),text=str(col),anchor='s',font=self.fonts['small'],fill=MUTED)
