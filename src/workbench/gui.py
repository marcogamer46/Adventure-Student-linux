"""GUI-first Adventure workbench; active runs and passive playback are separate."""
import json
from pathlib import Path
import queue
import threading
import time
import webbrowser

from src.framework.static_records import read_json
from src.renderer.expedition.display import initialize_display, inspect_display, named_fonts
from src.renderer.expedition.preview import PreviewBoard, WorldPreview, TerrainPreview, recorded_scene
from src.renderer.expedition.timeline import Timeline
from src.renderer.expedition.formatting import friendly_action
from .gui_services import (AttemptService, SelectedInput, SavedPlayback, ServiceError, content,
    select_scenario, scenario_variants, prepared_example, load_saved, load_generated, saved_runs, read_member)
from .gui_text import OBJECTS, REPAIR, requirements, points, failure_text, playback_feedback

BG,PANEL,INK,MUTED,ACCENT='#f1eee5','#fffdf8','#263f42','#566c6b','#206b66'
PHASES={'checking_sources':('Checking saved files','Reading your current saved source.'),
    'loading_components':('Checking components','The map stays at its initial state while your saved solution is checked.'),
    'running_solution':('Running your solution','Your saved code runs once. Playback is available after the saved result has been checked.'),
    'generating_terrain':('Generating terrain','Your saved terrain generator is working with the selected requirements.'),
    'generating_level':('Generating a level','Your saved level generator is using the selected terrain provider.'),
    'validating_result':('Checking the result','The workbench is validating this attempt before saving it.')}


class Workbench:
    def __init__(self,workspace):
        self.workspace=Path(workspace).resolve()
        self.content=content(self.workspace);self.rows=self.content['scenarios']
        self.service=AttemptService(self.workspace)
        self.selected=select_scenario(self.workspace,self.rows[0]);self.selected_row=self.rows[0]
        self.playback=None;self.timeline=None;self.playback_data=None
        self.active_token=None;self.attempt_input=None;self.own_attempt=False;self.mode='level'
        self.next_operation='solve';self.next_provider='reference'
        self.status_title='Ready to try';self.status_body='Choose a scenario, then run your solution. Unfinished code is expected while you learn.'
        self.last_error=None;self.stale=False;self.closed=False;self.closing=False;self.dialog=None
        self.root=None;self.after_ids={};self.source_checks=queue.Queue(maxsize=1);self.checking_source=False
        self.primary_armed_at=0.0
        self.gesture_seconds=.5

    def dp(self,n):return max(1,round(n*self.scale))

    def button(self,parent,text,command,*,primary=False):
        return self.tk.Button(parent,text=text,command=command,font=self.fonts['body'],
            bg=ACCENT if primary else PANEL,fg='white' if primary else INK,activebackground='#dce9df',
            activeforeground=INK,relief='flat',bd=0,padx=self.dp(10),pady=self.dp(8),takefocus=True,
            highlightthickness=2,highlightbackground=PANEL,highlightcolor=ACCENT)

    def label(self,parent,text='',*,font='body',background=PANEL,color=INK):
        return self.tk.Label(parent,text=text,font=self.fonts[font],bg=background,fg=color,
                             anchor='w',justify='left',padx=0,pady=0)

    def build(self,root,tk,*,startup=None):
        self.root,self.tk=root,tk;root.title('Adventure workbench');root.configure(bg=BG)
        import sys
        if sys.platform=='win32':
            import ctypes
            self.gesture_seconds=max(.2,min(1.0,ctypes.windll.user32.GetDoubleClickTime()/1000))
        self.scale=max(.75,min(3,float(root.winfo_fpixels('1i'))/96));self.fonts=named_fonts(root)
        root.option_add('*Font',self.fonts['body'])
        self.display=inspect_display(root,self.fonts,startup=startup)
        work=next((m['work_area'] for m in self.display.get('monitors',[]) if m['active']),None)
        width,height=(work[2]-work[0],work[3]-work[1]) if work else (root.winfo_screenwidth(),root.winfo_screenheight())
        root.geometry(f'{min(1366,width-self.dp(24))}x{min(768,height-self.dp(44))}')
        root.minsize(min(1040,width-self.dp(24)),min(620,height-self.dp(44)))
        root.grid_columnconfigure(0,weight=1);root.grid_rowconfigure(1,weight=1)
        root.protocol('WM_DELETE_WINDOW',self.close)
        header=tk.Frame(root,bg=PANEL,padx=self.dp(18),pady=self.dp(12));header.grid(row=0,column=0,sticky='ew')
        header.grid_columnconfigure(0,weight=1)
        title=self.label(header,'Adventure workbench',font='title');title.grid(row=0,column=0,sticky='w')
        nav=tk.Frame(header,bg=PANEL);nav.grid(row=0,column=1,sticky='e')
        self.navigation={}
        for label,callback in [('Scenarios',self.scenarios),('Test generators',self.generators),('Saved runs',self.history),('Help',self.help)]:
            button=self.button(nav,label,callback);button.pack(side='left',padx=(self.dp(4),0));self.navigation[label]=button
        def reflow(event):
            if event.widget is header:
                stacked=title.winfo_reqwidth()+nav.winfo_reqwidth()+self.dp(50)>event.width
                nav.grid(row=1 if stacked else 0,column=0 if stacked else 1,sticky='w' if stacked else 'e')
        header.bind('<Configure>',reflow)
        body=tk.Frame(root,bg=BG,padx=self.dp(18),pady=self.dp(12));body.grid(row=1,column=0,sticky='nsew')
        body.grid_rowconfigure(0,weight=1);body.grid_columnconfigure(0,weight=1)
        left=tk.Frame(body,bg=BG);left.grid(row=0,column=0,sticky='nsew',padx=(0,self.dp(16)))
        left.grid_columnconfigure(0,weight=1);left.grid_rowconfigure(3,weight=1)
        self.name=self.label(left,font='heading',background=BG);self.name.grid(row=0,column=0,sticky='ew')
        self.provenance=self.label(left,font='small',background=BG,color=MUTED);self.provenance.grid(row=1,column=0,sticky='ew',pady=(self.dp(7),self.dp(8)))
        controls=tk.Frame(left,bg=BG);controls.grid(row=2,column=0,sticky='ew',pady=(0,self.dp(5)))
        for text,command in [('Zoom out',lambda:self.board.zoom(.8)),('Zoom in',lambda:self.board.zoom(1.25)),('Fit map',lambda:self.board.fit())]:
            self.button(controls,text,command).pack(side='left',padx=(0,self.dp(4)))
        self.board=PreviewBoard(left,tk,self.fonts,self.workspace/'assets/presentation/asset-manifest-v2.json',scale=self.scale,on_inspect=self.inspect_entity)
        self.board.canvas.grid(row=3,column=0,sticky='nsew')
        self.caption=self.label(left,background=BG);self.caption.grid(row=4,column=0,sticky='ew',pady=(self.dp(10),self.dp(6)))
        self.transport=tk.Frame(left,bg=BG);self.transport.grid(row=5,column=0,sticky='ew')
        self.transport_buttons={}
        for i,(key,text,callback) in enumerate([('play','Play',self.toggle),('previous','Previous',lambda:self.seek(-1,relative=True)),
                ('next','Next',lambda:self.seek(1,relative=True)),('restart','Replay from start',lambda:self.seek(0))]):
            b=self.button(self.transport,text,callback);b.grid(row=0,column=i,sticky='w',padx=(0,self.dp(5)))
            self.transport_buttons[key]=b
        def transport_reflow(event):
            if event.widget is self.transport:
                buttons=list(self.transport_buttons.values());stack=sum(b.winfo_reqwidth()+self.dp(5) for b in buttons)>event.width
                for i,b in enumerate(buttons):b.grid(row=i//2 if stack else 0,column=i%2 if stack else i,pady=(0,self.dp(4)))
        self.transport.bind('<Configure>',transport_reflow)
        def wrap_left(event):
            if event.widget is left:
                for widget in (self.name,self.provenance,self.caption):widget.configure(wraplength=max(100,event.width))
        left.bind('<Configure>',wrap_left)
        side=tk.Frame(body,bg=PANEL,width=self.dp(276),padx=self.dp(16),pady=self.dp(16))
        side.grid(row=0,column=1,sticky='nsew');side.grid_propagate(False);side.grid_columnconfigure(0,weight=1);side.grid_rowconfigure(5,weight=1)
        self.label(side,'Your next step',font='heading').grid(row=0,column=0,sticky='ew',pady=(0,self.dp(12)))
        self.goal=self.label(side);self.goal.grid(row=1,column=0,sticky='ew',pady=(0,self.dp(12)))
        self.status=self.label(side,font='strong',color=ACCENT);self.status.grid(row=2,column=0,sticky='ew',pady=(0,self.dp(10)))
        self.primary=self.button(side,'Run solution',self.primary_action,primary=True);self.primary.grid(row=3,column=0,sticky='ew')
        self.save_hint=self.label(side,'Save edits in your IDE before running.',font='small',color=MUTED)
        self.save_hint.grid(row=4,column=0,sticky='ew',pady=(self.dp(7),self.dp(10)))
        feedback=tk.Frame(side,bg=PANEL);feedback.grid(row=5,column=0,sticky='nsew');feedback.grid_columnconfigure(0,weight=1);feedback.grid_rowconfigure(0,weight=1)
        self.feedback=tk.Text(feedback,width=1,height=1,wrap='word',bg=PANEL,fg=INK,font=self.fonts['body'],relief='flat',bd=0,padx=0,pady=0,takefocus=True)
        self.feedback.grid(row=0,column=0,sticky='nsew')
        scroll=tk.Scrollbar(feedback,command=self.feedback.yview);scroll.grid(row=0,column=1,sticky='ns');self.feedback.configure(yscrollcommand=scroll.set)
        self.watch=self.button(side,'Watch example',self.watch_example);self.watch.grid(row=6,column=0,sticky='ew',pady=(self.dp(8),self.dp(5)))
        self.rules=self.button(side,'Scenario rules',self.show_rules);self.rules.grid(row=7,column=0,sticky='ew')
        def wrap_side(event):
            if event.widget is side:
                for widget in (self.goal,self.status,self.save_hint):widget.configure(wraplength=max(80,event.width-self.dp(32)))
        side.bind('<Configure>',wrap_side)
        self.render();root.update_idletasks();self.primary.focus_set();self.schedule('poll',40,self.poll);self.schedule('source',1500,self.check_source)
        return self

    def schedule(self,key,delay,fn):
        if self.closed:return
        old=self.after_ids.pop(key,None)
        if old is not None:self.root.after_cancel(old)
        def invoke():
            self.after_ids.pop(key,None)
            if not self.closed:fn()
        self.after_ids[key]=self.root.after(delay,invoke)

    def inspect_entity(self,text):self.text_dialog('Selected entity',text)
    def busy(self):return self.active_token is not None

    def select(self,row):
        if self.busy():raise ServiceError('ATTEMPT_BUSY')
        selected=select_scenario(self.workspace,row)
        self.pause();self.selected=selected;self.selected_row=row;self.playback=self.timeline=self.playback_data=None
        self.own_attempt=False;self.mode='level';self.stale=False;self.last_error=None
        self.next_operation='solve';self.next_provider='reference'
        self.status_title,self.status_body='Ready to try','Choose a scenario, then run your solution. Unfinished code is expected while you learn.'
        self.render();self.primary.focus_set()

    def primary_action(self):
        # One mouse double-click is one Run intent, even if TODO detection
        # finishes before its second click. Cancel arms after that gesture.
        if time.monotonic()<self.primary_armed_at:return
        if self.busy():
            if self.service.cancel():self.status_title,self.status_body='Cancelling run…','Waiting for this attempt to stop.'
            self.render();return
        self.start(self.next_operation,self.next_provider)

    def start(self,operation='solve',provider='reference'):
        if self.busy():return
        self.next_operation,self.next_provider=operation,provider
        self.pause();self.playback=self.timeline=self.playback_data=None;self.stale=False;self.last_error=None
        if operation=='solve':self.own_attempt=True
        self.status_title,self.status_body=PHASES['checking_sources'];self.attempt_input=self.selected.identity
        self.primary_armed_at=time.monotonic()+self.gesture_seconds
        self.schedule('arm-primary',round(self.gesture_seconds*1000)+10,self.render)
        try:self.active_token=self.service.start(self.selected,operation=operation,provider=provider)
        except (OSError,ValueError):self.status_title,self.status_body='The attempt could not start','Open Setup & repair and Support details, then retry.'
        self.render()

    def poll(self):
        while True:
            try:event=self.service.events.get_nowait()
            except queue.Empty:break
            if event['token']!=self.active_token or event['input_identity']!=self.attempt_input:continue
            if event['event']=='phase':
                if self.status_title!='Cancelling run…':self.status_title,self.status_body=PHASES.get(event['phase'],PHASES['validating_result'])
            else:
                self.active_token=None
                if event['event']=='error':self.last_error=event;self.status_title,self.status_body=failure_text(event)
                elif isinstance(event['result'],SavedPlayback):self.set_playback(event['result'])
                else:
                    self.selected=event['result'];self.mode='terrain' if self.selected.kind=='terrain_only' else 'level'
                    self.next_operation='terrain' if self.mode=='terrain' else 'solve'
                    self.status_title='Terrain is valid' if self.mode=='terrain' else 'Level is valid'
                    self.status_body='The floor plan meets the selected requirements. Controller not required.' if self.mode=='terrain' else 'The level is ready to test with your controller. No run has started.'
            self.render()
        try:
            identity,stale=self.source_checks.get_nowait()
            if self.playback is not None and self.playback.source_identity==identity and not self.playback.example:
                if self.stale!=stale:self.stale=stale;self.render()
        except queue.Empty:pass
        if self.closing and not self.service.busy:self.destroy();return
        self.schedule('poll',40,self.poll)

    def set_playback(self,playback):
        self.playback=playback;self.selected=playback.selected;self.mode='level'
        self.next_operation='solve';self.next_provider='reference'
        self.timeline=Timeline(playback.presentation());self.playback_data=read_json(playback.raw)
        self.status_title='Example playback' if playback.example else 'Saved playback'
        self.status_body='Play and Next inspect recorded actions. '+('Run solution' if playback.example and not self.own_attempt else 'Run again')+' executes your current saved code.'

    def scene(self):
        if self.timeline is not None:return recorded_scene(self.timeline.recording,self.timeline.current)
        if self.mode=='terrain':
            from src.framework.generation.canonical import read_terrain
            terrain=read_terrain(read_json(self.selected.raw)['terrain']) if self.selected.kind=='terrain_only' else self.selected.level().terrain
            return TerrainPreview.from_terrain(terrain).scene
        return WorldPreview.from_level(self.selected.level()).scene

    def render(self):
        if self.root is None or self.closed:return
        self.name.configure(text=self.selected.name)
        self.board.set_scene(self.scene())
        terrain=self.mode=='terrain';busy=self.busy();title,body=self.status_title,self.status_body
        provenance='Scenario preview — not run yet';caption='Initial map • no actions taken';metrics=''
        if terrain:
            provenance='Generated terrain • controller not required' if self.selected.kind=='terrain_only' else 'Terrain requirements preview • not generated output'
            caption='Floor plan only • no endpoints or entities'
            rows=self.scene().terrain;metrics=f'Observed preview: {len(rows)} rows × {len(rows[0])} columns; {sum(r.count(".") for r in rows)} floor cells.'
        elif self.selected.kind=='generated_level':provenance='Generated level preview • controller has not run.'
        elif self.next_operation=='level':provenance='Generation requirements preview • no generated level yet'
        if self.timeline is not None:
            frame=self.timeline.current;record=self.timeline.recording;index=frame.index
            provenance='Example replay — not your solution.' if self.playback.example else 'Saved result • your code'
            caption=f'{friendly_action(frame)} • frame {index+1} of {len(record.frames)}'
            if frame.accepted is False:caption='Rejected intention: '+caption
            events=self.playback_data['events'][:index]
            penalty=sum(e['encounter_penalty'] for e in events);reward=sum(e['artifact_reward'] for e in events)
            metrics=f'Actions taken: {frame.turn}\nEncounter cost: {penalty}\nArtifact points: {reward}\nTotal cost: {frame.turn+penalty}'
            if index==len(record.frames)-1:
                summary=self.playback_data['summary'];metrics+=f'\nPoints earned: {summary["score"]}'
            feedback=playback_feedback(record,frame)
            if feedback is not None:title,body=feedback
            if self.stale:body='Code changed — run again. This recording was made before your latest saved changes. Playback still shows that earlier run.\n\n'+body
        self.provenance.configure(text=provenance);self.caption.configure(text=caption)
        self.goal.configure(text='Produce a floor plan that meets the selected requirements.' if terrain else 'Reach the exit, then return EXIT.')
        self.status.configure(text=title)
        primary_text=('Cancel run' if busy else 'Generate terrain' if self.next_operation=='terrain' else
            'Generate level' if self.next_operation=='level' else 'Run again' if self.own_attempt else 'Run solution')
        self.primary.configure(text=primary_text,state='disabled' if self.closing or time.monotonic()<self.primary_armed_at else 'normal')
        self.save_hint.configure(text='Save generator edits before checking.' if terrain else 'Save edits in your IDE before running.')
        self.feedback.configure(state='normal');self.feedback.delete('1.0','end');self.feedback.insert('1.0',body+('\n\n'+metrics if metrics else ''));self.feedback.configure(state='disabled')
        self.rules.configure(text='Terrain requirements' if terrain else 'Scenario rules')
        if terrain:self.watch.grid_remove()
        else:
            self.watch.grid();self.watch.configure(state='normal' if not busy and self.selected_row and self.selected_row.get('prepared_example') and self.selected.kind=='public_scenario' else 'disabled')
        for key,button in self.transport_buttons.items():
            enabled=self.timeline is not None and not busy
            if key=='previous' and enabled:enabled=self.timeline.index>0
            if key=='next' and enabled:enabled=not self.timeline.at_end
            button.configure(state='normal' if enabled else 'disabled')
        self.transport_buttons['play'].configure(text='Pause' if self.timeline is not None and self.timeline.playing else 'Play')

    def pause(self):
        if self.timeline is not None:self.timeline.pause()
        if self.root is not None:
            old=self.after_ids.pop('play',None)
            if old is not None:self.root.after_cancel(old)

    def toggle(self):
        if self.timeline is None or self.busy():return
        if self.timeline.playing:self.pause()
        else:self.timeline.play();self.schedule('play',self.timeline.delay_ms,self.tick)
        self.render()

    def tick(self):
        if self.timeline is None or not self.timeline.playing:return
        self.timeline.tick();self.render()
        if self.timeline.playing:self.schedule('play',self.timeline.delay_ms,self.tick)

    def seek(self,index,*,relative=False):
        if self.timeline is None or self.busy():return
        self.pause();self.timeline.seek(self.timeline.index+index if relative else index);self.render()

    def check_source(self):
        if self.playback is not None and not self.playback.example and not self.checking_source:
            identity=self.playback.source_identity;self.checking_source=True
            def check():
                try:
                    from src.framework.submission.identity import capture_sources
                    from src.framework.public_practice.records import identity_from_files
                    manifest=capture_sources(self.workspace)
                    current=identity_from_files({p['path']:p['sha256'] for p in manifest['sources']})['sha256']
                    try:self.source_checks.put_nowait((identity,current!=identity))
                    except queue.Full:pass
                except (OSError,ValueError):
                    try:self.source_checks.put_nowait((identity,True))
                    except queue.Full:pass
                finally:self.checking_source=False
            threading.Thread(target=check,daemon=True).start()
        self.schedule('source',1500,self.check_source)

    def dialog_shell(self,title):
        if self.dialog is not None:self.dialog.lift();return None
        self.pause();self.render();focus=self.root.focus_get();tk=self.tk
        win=tk.Toplevel(self.root);win.title(title);win.configure(bg=PANEL);win.transient(self.root)
        win.geometry(f'{min(850,self.root.winfo_width()-60)}x{min(620,self.root.winfo_height()-50)}')
        win.grid_rowconfigure(0,weight=1);win.grid_columnconfigure(0,weight=1);self.dialog=win
        area=tk.Frame(win,bg=PANEL,padx=self.dp(16),pady=self.dp(12));area.grid(row=0,column=0,sticky='nsew')
        footer=tk.Frame(win,bg=PANEL,padx=self.dp(16),pady=self.dp(8));footer.grid(row=1,column=0,sticky='ew')
        def close():
            self.dialog=None;win.grab_release();win.destroy()
            if focus is not None and focus.winfo_exists():focus.focus_set()
        self.button(footer,'Close',close).pack(side='right');win.protocol('WM_DELETE_WINDOW',close);win.bind('<Escape>',lambda _e:close())
        win.grab_set();return win,area,footer,close

    def text_dialog(self,title,text):
        shell=self.dialog_shell(title)
        if shell is None:return
        win,area,footer,close=shell;area.grid_rowconfigure(0,weight=1);area.grid_columnconfigure(0,weight=1)
        body=self.tk.Text(area,wrap='word',bg=PANEL,fg=INK,relief='flat',font=self.fonts['body'],padx=self.dp(4),pady=self.dp(4),width=1,height=1)
        body.grid(row=0,column=0,sticky='nsew');scroll=self.tk.Scrollbar(area,command=body.yview);scroll.grid(row=0,column=1,sticky='ns')
        body.configure(yscrollcommand=scroll.set);body.insert('1.0',text);body.configure(state='disabled');body.focus_set()
        return footer

    def scenarios(self):
        shell=self.dialog_shell('Scenarios')
        if shell is None:return
        from tkinter import ttk
        win,area,footer,close=shell;area.grid_columnconfigure(0,weight=1);area.grid_rowconfigure(3,weight=1)
        self.label(area,'Choose a public scenario',font='heading').grid(row=0,column=0,sticky='w',pady=(0,self.dp(10)))
        search=self.tk.StringVar(win);entry=self.tk.Entry(area,textvariable=search,relief='solid',bd=1);entry.grid(row=1,column=0,sticky='ew')
        collection=self.tk.StringVar(win,value='All scenarios')
        chooser=ttk.Combobox(area,state='readonly',textvariable=collection,values=['All scenarios','Guide and public worlds','Public family variations']);chooser.grid(row=2,column=0,sticky='ew',pady=self.dp(8))
        box=self.tk.Listbox(area,exportselection=False,relief='flat',bg=BG,fg=INK,selectbackground=ACCENT,selectforeground='white',width=1,height=1)
        box.grid(row=3,column=0,sticky='nsew');scroll=self.tk.Scrollbar(area,command=box.yview);scroll.grid(row=3,column=1,sticky='ns');box.configure(yscrollcommand=scroll.set)
        shown=[];reverse=self.tk.BooleanVar(win,value=False)
        reverse_box=self.tk.Checkbutton(area,text='Swap start and exit',variable=reverse,bg=PANEL,state='disabled')
        reverse_box.grid(row=4,column=0,sticky='w',pady=self.dp(6))
        def selected_variation(*_):
            reverse.set(False)
            allowed=bool(box.curselection() and shown[box.curselection()[0]].get('alternate'))
            reverse_box.configure(state='normal' if allowed and not self.busy() else 'disabled')
        def update(*_):
            shown[:]=[r for r in self.rows if search.get().casefold() in r['name'].casefold() and (collection.get()=='All scenarios' or r['collection']==collection.get())]
            box.delete(0,'end')
            for row in shown:box.insert('end',row['name'])
            if shown:box.selection_set(0)
            selected_variation()
        def select():
            if self.busy() or not box.curselection():return
            row=shown[box.curselection()[0]]
            if reverse.get():row=row['alternate']
            try:self.select(row)
            except (OSError,ValueError):close();self.text_dialog('Scenario unavailable','The public input did not pass its readback check. Restore the complete project files.');return
            close();self.primary.focus_set()
        select_button=self.button(footer,'Select scenario',select,primary=True);select_button.pack(side='left')
        if self.busy():
            select_button.configure(state='disabled')
            self.label(area,'Cancel the active run before selecting another scenario.',font='small').grid(row=5,column=0,sticky='ew')
        box.bind('<<ListboxSelect>>',selected_variation)
        search.trace_add('write',update);chooser.bind('<<ComboboxSelected>>',update);box.bind('<Double-Button-1>',lambda _e:select());update();entry.focus_set()

    def watch_example(self):
        if self.busy() or not self.selected_row:return
        try:self.set_playback(prepared_example(self.workspace,self.selected_row));self.stale=False;self.last_error=None;self.render()
        except (OSError,ValueError):self.text_dialog('Example unavailable','The prepared example did not pass its input and recording checks. No student code was run.')

    def generators(self):
        if self.busy():self.text_dialog('Run in progress','Cancel the active attempt before testing generators.');return
        shell=self.dialog_shell('Test generators')
        if shell is None:return
        from tkinter import ttk
        win,area,footer,close=shell;area.grid_columnconfigure(0,weight=1);area.grid_rowconfigure(5,weight=1)
        options=[r for r in self.rows if r['collection']=='Public family variations' and not r['slug'].startswith('family-ADV-T8-')]
        self.label(area,'Test one generator responsibility',font='heading').grid(row=0,column=0,sticky='w',pady=(0,self.dp(12)))
        kind=self.tk.StringVar(win,value='terrain');provider=self.tk.StringVar(win,value='Provided terrain generator')
        self.tk.Radiobutton(area,text='Terrain: floor plan only',variable=kind,value='terrain',bg=PANEL).grid(row=1,column=0,sticky='w')
        self.tk.Radiobutton(area,text='Level: assemble a world',variable=kind,value='level',bg=PANEL).grid(row=2,column=0,sticky='w')
        requirement=ttk.Combobox(area,state='readonly',values=[r['name'] for r in options]);requirement.current(0);requirement.grid(row=3,column=0,sticky='ew',pady=self.dp(12))
        provider_box=ttk.Combobox(area,textvariable=provider,values=['Provided terrain generator','My terrain generator'],state='disabled');provider_box.grid(row=4,column=0,sticky='ew')
        note_area=self.tk.Frame(area,bg=PANEL);note_area.grid(row=5,column=0,sticky='nsew',pady=self.dp(12))
        note_area.grid_columnconfigure(0,weight=1);note_area.grid_rowconfigure(0,weight=1)
        note=self.tk.Text(note_area,wrap='word',bg=PANEL,fg=INK,font=self.fonts['body'],relief='flat',width=1,height=1,takefocus=True)
        note.grid(row=0,column=0,sticky='nsew');note_scroll=self.tk.Scrollbar(note_area,command=note.yview)
        note_scroll.grid(row=0,column=1,sticky='ns');note.configure(yscrollcommand=note_scroll.set)
        def set_note(text):
            note.configure(state='normal');note.delete('1.0','end');note.insert('1.0',text);note.configure(state='disabled');note.yview_moveto(0)
        def update(*_):
            provider_box.configure(state='readonly' if kind.get()=='level' else 'disabled')
            set_note(('TerrainGenerator produces geometry only. Other components can remain unfinished.' if kind.get()=='terrain' else 'Provided terrain isolates level assembly. My terrain tests the dependency between your two generators. AgentController can remain unfinished.')+' Each named variation uses its published seed and requirements.')
            generate.configure(text='Generate terrain' if kind.get()=='terrain' else 'Generate level')
        def generate_now():
            row=options[requirement.current()];operation=kind.get();dependency='reference' if provider.get()=='Provided terrain generator' else 'student'
            self.select(row);self.mode='terrain' if operation=='terrain' else 'level';close();self.start(operation,dependency)
        generate=self.button(footer,'Generate terrain',generate_now,primary=True);generate.pack(side='left')
        kind.trace_add('write',update);update()
        self.button(area,'View selected requirements',lambda:set_note(requirements(select_scenario(self.workspace,options[requirement.current()]),terrain_only=kind.get()=='terrain'))).grid(row=6,column=0,sticky='w')

    def history(self):
        if self.busy():self.text_dialog('Run in progress','Cancel the active attempt before opening another saved result.');return
        shell=self.dialog_shell('Saved runs')
        if shell is None:return
        win,area,footer,close=shell;area.grid_columnconfigure(0,weight=1);area.grid_rowconfigure(1,weight=1)
        self.label(area,'Saved attempts and generated inputs',font='heading').grid(row=0,column=0,sticky='w',pady=(0,self.dp(10)))
        items=[(path,'run',label) for path,label in saved_runs(self.workspace)]
        base=self.workspace/'practice'
        if base.exists() and not base.is_symlink() and not getattr(base,'is_junction',lambda:False)():
            for p in sorted(base.glob('gui-*'),reverse=True)[:256]:
                try:
                    attempt=read_json(read_member(self.workspace,p.relative_to(self.workspace).as_posix()+'/attempt.json',limit=65536))
                    if type(attempt) is dict and attempt.get('status')=='GENERATED' and attempt.get('kind') in {'terrain','level'}:
                        items.append((p.relative_to(self.workspace).as_posix(),'generated','Generated '+attempt['kind']+' • '+p.name[4:19]))
                except (OSError,ValueError,TypeError):continue
        box=self.tk.Listbox(area,exportselection=False,relief='flat',bg=BG,fg=INK,width=1,height=1);box.grid(row=1,column=0,sticky='nsew')
        scroll=self.tk.Scrollbar(area,command=box.yview);scroll.grid(row=1,column=1,sticky='ns');box.configure(yscrollcommand=scroll.set)
        for _,_,label in items:box.insert('end',label)
        if items:box.selection_set(0)
        def open_item():
            if not box.curselection():return
            path,kind,_=items[box.curselection()[0]]
            try:
                if kind=='run':self.set_playback(load_saved(self.workspace,path));self.own_attempt=True
                else:
                    self.pause();self.playback=self.timeline=self.playback_data=None;self.selected=load_generated(self.workspace,path)
                    self.mode='terrain' if self.selected.kind=='terrain_only' else 'level'
                    self.next_operation='terrain' if self.mode=='terrain' else 'solve'
                    self.status_title='Terrain is valid' if self.mode=='terrain' else 'Level is valid';self.status_body='This is the stored generated input. A controller run uses current saved code without regenerating it.'
                self.selected_row=next((r for r in scenario_variants(self.rows) if r['slug']==self.selected.slug),None)
                self.stale=False;self.last_error=None;self.render();close()
            except (OSError,ValueError):close();self.text_dialog('Saved item unavailable','Its input, recording, or required companions did not pass validation. It was not replayed.')
        self.button(footer,'Open saved item',open_item,primary=True).pack(side='left')
        if not items:self.label(area,'No saved runs yet. Run a solution or test a generator first.').grid(row=2,column=0,sticky='ew')

    def show_rules(self):self.text_dialog('Terrain requirements' if self.mode=='terrain' else 'Scenario rules',requirements(self.selected,terrain_only=self.mode=='terrain'))

    def help(self):
        shell=self.dialog_shell('Help')
        if shell is None:return
        win,area,footer,close=shell
        actions=[('Meet the objects',lambda:self.text_dialog('Meet the objects',OBJECTS)),('Selected guide example',self.open_guide),
            ('Terrain requirements' if self.mode=='terrain' else 'Scenario rules',self.show_rules)]
        if self.mode!='terrain':actions.append(('How points work',lambda:self.text_dialog('How points work',points(self.selected))))
        actions += [('Setup & repair',lambda:self.text_dialog('Setup & repair',REPAIR)),('Support details',self.support)]
        for i,(label,fn) in enumerate(actions):
            def launch(callback=fn):close();callback()
            self.button(area,label,launch).grid(row=i,column=0,sticky='ew',pady=self.dp(4))
        area.grid_columnconfigure(0,weight=1)

    def open_guide(self):
        path=self.workspace/'GUIDE.html'
        if not path.is_file():self.text_dialog('Guide unavailable','The offline guide is missing. Restore the complete project package.');return
        if self.selected.guide_anchor:
            webbrowser.open(path.as_uri()+'#'+self.selected.guide_anchor);return
        if self.mode=='terrain':anchor='meet-the-objects'
        else:
            level=self.selected.level();topology=self.selected.configuration['specification']['terrain_spec']['topology'].lower()
            anchor=('enemy-or-longer-route' if level.enemies else 'path-with-artifacts' if level.artifacts
                    else 'first-bend' if 'bent' in topology else 'reach-the-exit' if 'straight' in topology else 'two-cycle-routes')
        footer=self.text_dialog('Selected scenario guide',self.selected.name+'\n\n'+requirements(self.selected,terrain_only=self.mode=='terrain')+
            '\n\nThis is a public variation. Use its own rules above, then open the related base explanation in the seven-case guide.')
        if footer is not None:
            self.button(footer,'Open related guide example',lambda:webbrowser.open(path.as_uri()+'#'+anchor)).pack(side='left')

    def support(self):
        details=dict(scope='LOCAL_PUBLIC_PRACTICE_NO_GRADE',input_kind=self.selected.kind,input_identity=self.selected.identity,
            active_attempt=self.active_token,code_changed=self.stale)
        if self.last_error:details['attempt']={k:self.last_error.get(k) for k in ('status','code','diagnostic','resources')}
        if self.playback:details['recording']=dict(source_identity=self.playback.source_identity,prepared_example=self.playback.example)
        if self.selected.generation:details['generation']=read_json(self.selected.generation)
        footer=self.text_dialog('Support details',json.dumps(details,indent=2,ensure_ascii=False))
        if footer is not None:
            self.button(footer,'Export diagnostics',lambda:self.export_details(details)).pack(side='left')

    def export_details(self,details):
        from .__main__ import destination,reserve,atomic
        from src.framework.static_records import encode
        import uuid
        path=destination('practice/diagnostics-'+uuid.uuid4().hex+'.json',self.workspace)
        try:
            reserve(path);atomic(path,encode(details))
            from tkinter import messagebox
            messagebox.showinfo('Diagnostic report saved','Saved in practice as '+path.name+'.',parent=self.dialog or self.root)
        except (OSError,ValueError):
            from tkinter import messagebox
            messagebox.showerror('Diagnostic report unavailable','The report could not be written. Check project folder permissions.',parent=self.dialog or self.root)

    def close(self):
        if self.closed:return
        if self.service.busy:
            from tkinter import messagebox
            if not messagebox.askyesno('Cancel this attempt?','Cancel the active attempt and close after it stops?',parent=self.root):return
            self.closing=True;self.service.cancel();self.status_title,self.status_body='Cancelling run…','The workbench will close after owned cleanup.';self.render();return
        self.destroy()

    def destroy(self):
        if self.closed:return
        self.pause();self.closed=True
        for identifier in self.after_ids.values():self.root.after_cancel(identifier)
        self.after_ids.clear();self.root.destroy()


def main(workspace):
    startup=initialize_display()
    import tkinter as tk
    root=tk.Tk()
    try:
        app=Workbench(workspace);app.build(root,tk,startup=startup);root.mainloop()
    except BaseException:
        if root.winfo_exists():root.destroy()
        raise
    return 0
