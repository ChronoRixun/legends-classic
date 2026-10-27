"""Original online menu authoring and offline fixture controller (round 1).

No network/clipboard/save services and no new production script registrations.
Fixture intents are data consumed by a future test harness, never console source.
Coordinates are the approved 640 x 480 canvas; scene conversion uses 512 x 384.
"""
from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field as dc_field

from . import menu_theme as T, menu_conversion as M

MENUS = ('lc_online', 'lc_host', 'lc_code', 'lc_browse')
NATIVE_ENTRY = 'openmenu online'
ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
PALETTE = ('0A1830','11284A','2A4A78','7FA6D9','EEF3FA','FFCB3D','54D68A','FF6F55')
STYLES = {'title': ('big',37), 'row': ('medium',15), 'body': ('medium',12.5), 'label': ('medium',11)}
COLUMNS = ((59,128),(188,67),(255,93),(348,58),(406,76),(482,78),(560,37))
PROMPT_TOKENS = {'back':'$MENU_BACK','delete':'$MENU_BACK','paste':'$MENU_NEXT',
                 'refresh':'$MENU_NEXT','rejoin':'$MENU_NEXT','clear':'$MENU_OTHER',
                 'name':'$MENU_OTHER','change':'$MENU_OTHER','open':'$MENU_OK'}


def field(text, limit):
    """Bound bytes and prevent renderer/console controls before presentation."""
    text = re.sub(r'[\x00-\x1f\x7f$#~|;"%]', '', str(text).encode('ascii','replace').decode())
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:max(0,limit-3)].rstrip() + '...'


def synthetic_rooms():
    # Invented room records, never contactable peers or assigned release identities.
    rows = [('Weekend co-op','Logan','Mansion',2,'In lobby',True,False),
            ("Kitty's game",'Kitty','Sewers',3,'In progress',True,False),
            ('Danger Room night','Sam','Danger Room',1,'In lobby',True,False),
            ('Late shift','Bobby','Sub-basement',2,'In progress',True,False),
            ("Pietro's game",'Pietro','Astral plane',1,'Loading',True,False),
            ("Alex's game",'Alex','HAARP',4,'Full',True,False),
            ('Friday run','Ororo','Nuclear plant',2,'In lobby',False,False),
            ('A very long synthetic room name','A very long host name','A very long synthetic area',1,'In lobby',True,False),
            ('Old listing','Test','Mansion',2,'Stale',True,True)]
    return [dict(zip(('name','host','area','players','status','same','stale'),r)) for r in rows]


@dataclass
class Fixture:
    menu: str = 'lc_online'
    code: str = 'K7QN2X'
    selected: int = 0
    offset: int = 0
    rooms: list = dc_field(default_factory=synthetic_rooms)
    error: str = ''
    phase: str = 'fixture idle'
    visibility: str = 'PRIVATE'
    campaign: str = 'LOAD SAVED CAMPAIGN'
    drop_in: bool = True
    members: tuple = ('Logan', 'Kitty', 'Alex')

    def rebound(self):
        self.rooms=self.rooms[:50]
        self.selected = max(0,min(self.selected,len(self.rooms)-1))
        self.offset = max(0,min(self.offset,max(0,len(self.rooms)-7)))
        if self.selected < self.offset: self.offset=self.selected
        if self.selected >= self.offset+7: self.offset=self.selected-6

    def dispatch(self, intent, payload=None):
        """Deterministic H-level transitions. Never calls a native/network service."""
        if intent not in command_manifest(): raise ValueError('unknown fixture intent')
        if intent.startswith('open:'):
            self.menu=intent[5:]; self.error=''
        elif intent.startswith('code:'):
            if len(self.code)<8: self.code+=intent[5:]
            self.phase='resolved fixture' if len(self.code)==8 else 'editing fixture'
        elif intent in ('delete','back'):
            if intent=='delete' or (self.menu=='lc_code' and self.code): self.code=self.code[:-1]
            elif intent=='back': self.menu='lc_online'
        elif intent=='clear': self.code=''; self.phase='editing fixture'
        elif intent=='paste':
            text=(payload or '').strip().upper().replace('-','')
            if len(text)!=8 or any(c not in ALPHABET for c in text): self.error='Invalid code. Ask the host for eight characters.'
            else: self.code=text; self.error=''; self.phase='resolved fixture'
        elif intent=='done':
            if len(self.code)==8: self.phase='resolved fixture'
            else: self.error='Enter all eight characters.'
        elif intent.startswith('scroll:'): self.selected+=int(intent[7:]); self.rebound()
        elif intent.startswith('page:'):
            row=self.selected-self.offset
            self.offset=max(0,min(self.offset+7*int(intent[5:]),max(0,len(self.rooms)-7)))
            self.selected=self.offset+row; self.rebound()
        elif intent.startswith('select:'): self.selected=self.offset+int(intent[7:]); self.rebound()
        elif intent=='join':
            self.rebound()
            r=self.rooms[self.selected] if self.rooms else None
            if not r or r['players']==4 or not r['same'] or r['stale'] or r['status']=='Loading':
                self.error='This fixture room cannot be joined. Choose another game.'
            else: self.error=''; self.phase='resolved fixture'
        elif intent=='visibility': self.visibility='PUBLIC' if self.visibility=='PRIVATE' else 'PRIVATE'
        elif intent=='campaign': self.campaign='NEW CAMPAIGN' if self.campaign.startswith('LOAD') else 'LOAD SAVED CAMPAIGN'
        elif intent=='drop-in': self.drop_in=not self.drop_in
        elif intent=='open-room': self.phase='host preview fixture'
        elif intent=='error': self.error="Can't reach the online service. Try again or use Other ways to play."
        elif intent in ('dismiss','refresh'): self.error=''
        elif intent=='rejoin': self.menu='lc_code'; self.code='K7QN2X9M'; self.phase='resolved fixture'
        elif intent=='name': self.phase='native name intent fixture'
        elif intent=='room-name': self.phase='room name intent fixture'
        elif intent=='other': self.phase='native fallback intent fixture'
        elif intent=='party': self.error='No party yet.'


def command_manifest():
    return tuple(['open:'+m for m in MENUS]+['code:'+c for c in ALPHABET]+
                 ['select:'+str(i) for i in range(7)]+
                 ['delete','back','clear','paste','done','scroll:1','scroll:-1','page:1','page:-1','join','visibility',
                  'campaign','drop-in','open-room','error','dismiss','refresh','rejoin','name','room-name','other','party'])


def theme(colors, styles):
    original=ET.Element('colors')
    for i,h in enumerate(PALETTE):
        rgb=[int(h[j:j+2],16)/255 for j in (0,2,4)]
        ET.SubElement(original,'color',value=' '.join(format(v,'.9g') for v in (*rgb,.92 if i==1 else 1)))
    requests=[T.text_style('lc_o_'+name,font=font,normal=4 if name!='label' else 3,
                           focus=0,disabled=3,allow=True) for name,(font,_) in STYLES.items()]
    # All eight entries are part of this family, including model/status colours.
    for attrs, pair in zip(requests,((4,3),(5,3),(6,7),(2,1))):
        attrs['color_highlight'],attrs['color_disabled']=pair
    result=T.allocate(colors,styles,original,requests,color_reserve=4,style_reserve=4)
    if len(result[0])>T.COLOR_LIMIT or len(result[1])>T.STYLE_LIMIT:
        raise ValueError('online family exceeds native capacity')
    return result


def layout(name, state=None):
    if name not in MENUS: raise ValueError('unknown online menu')
    s=state or Fixture(); s.rebound()
    screen={'name':name,'items':[],'shapes':[],'focus':'','fixture_only':True}
    items, shapes=screen['items'],screen['shapes']
    def shape(kind,rect,color,**kw): shapes.append(dict(kind=kind,rect=rect,color=color,**kw))
    def text(key,value,x,y,w,h=18,style='body',color=4,intent='',enabled=True):
        items.append(dict(name=key,text=value,rect=(x,y,w,h),style=style,color=color,intent=intent,enabled=enabled))
    def button(key,value,rect,intent,enabled=True,primary=False):
        shape('rect' if name=='lc_code' else 'bar',rect,4 if primary else 2,dim=not enabled)
        x,y,w,h=rect; pad=4 if name=='lc_code' and key.startswith('key_') else 8 if name=='lc_code' and key in ('paste','clear','done') else 15
        text(key,value,x+pad,y+6,w-2*pad,h-9,'row',0 if primary else 4,intent,enabled)
        if name=='lc_code' and key.startswith('key_'): items[-1]['align']='center'
    def panel(key,title,rect):
        shape('panel',rect,1); x,y,w,h=rect
        
        if title: shape('rect',(x,y,w,22),2)
        
        if key!='self_header': shape('notch',(x,y,11,11),5)
        if title: text(key,title,x+16,y+7,w-30,13,'label')
    title,subtitle={'lc_online':('PLAY ONLINE','Play the campaign with up to four players'),
        'lc_host':('HOST A GAME','Friends join with your code; a public game is listed for anyone'),
        'lc_code':('JOIN BY CODE','Type the 8-character code your host sent you'),
        'lc_browse':('BROWSE GAMES',"Public games connect players directly: everyone can see each other's internet address")}[name]
    text('brand','LEGENDS CLASSIC',104 if name!='lc_online' else 62,25,270,14,'label',3)
    if name!='lc_online': shape('bar',(43,24,55,16),5)
    else:
        shape('slash',(43,24,3,13),5); shape('slash',(50,24,3,13),5,dim=True)
    if name!='lc_online': text('online_tag','ONLINE',51,26,43,13,'label',0)
    text('title',title,43,45,520,43,'title')
    shape('bar',(43,81 if name=='lc_online' else 83,107,4),5)
    text('subtitle',subtitle,43,95,554,20,'body',3)
    if name!='lc_online':
        panel('self_header','', (490,24,107,40))
        text('self_name','Sam' if name=='lc_code' else 'Logan',528,30,64,15,'row')
        text('self_state','Connected',538,46,58,13,'label',6)
        shape('bar',(500,31,20,26),2)
        text('self_initial','S' if name=='lc_code' else 'L',503,34,20,22,'row')
        shape('diamond',(529,49,7,6),6)
    if name=='lc_online':
        rows=[('host','HOST A GAME','Private or public','open:lc_host',True),
              ('code','JOIN BY CODE','8 characters','open:lc_code',True),
              ('browse','BROWSE GAMES','9 fixture games','open:lc_browse',True),
              ('party','PARTY','No party yet','party',False),
              ('other','OTHER WAYS TO PLAY','LAN, IP','other',True)]
        for i,(key,label,hint,intent,enabled) in enumerate(rows):
            button(key,label,(43,133+39*i,266,31),intent,enabled)
            # Anchor the hints at the approved right edge. The earlier 70-unit
            # left-aligned box discarded the unused space between label and hint.
            text(key+'_hint',hint,181,142+39*i,113,15,'label',3)
            items[-1].update(align='right',selected_with=key)
        panel('help_header','HOST A GAME',(43,334,266,74))
        shapes[:]=[q for q in shapes if q['rect']!=(43,334,266,22)]
        next(e for e in items if e['name']=='help_header').update(color=5,rect=(59,348,240,14))
        text('help','Open a private room and share its code with friends,',59,365,240,17)
        text('help2','or list it so anyone can join.',59,382,240,17)
        panel('you_header','YOU',(338,133,259,120))
        text('name_label','SCREEN NAME',354,166,220,13,'label',3)
        text('local_name','LOGAN',354,181,140,25,'title')
        text('change_name','$MENU_OTHER Change',535,185,59,18,'body',4,'name')
        text('service_label','ONLINE SERVICE',354,214,220,13,'label',3)
        text('service','Connected',367,229,200,18,'row',6)
        shape('diamond',(355,232,7,6),6)
        panel('last_header','LAST GAME',(338,262,259,75))
        text('last_name','Weekend co-op',354,295,180,19,'row')
        text('last_code','Code K7QN-2X9M, 2 hours ago',354,314,220,15,'body',3)
        text('rejoin','$MENU_NEXT Rejoin',539,301,55,17,'body',4,'rejoin')
        text('identity','Installed build: fixture (no release assigned)',338,406,259,15,'label',3)
        items[-1]['align']='right'
        screen['focus']='host'
    elif name=='lc_host':
        panel('settings_header','ROOM SETTINGS',(43,133,337,207))
        for y in (201,248,294): shape('rect',(43,y,337,1),3,dim=True)
        for key,label,y in (('visibility','VISIBILITY',174),('room_name','ROOM NAME',221),('campaign','CAMPAIGN',267),('drop','DROP-IN',314)):
            text(key+'_label',label,59,y,88,15,'label',3)
        shape('rect',(148,167,65,23),4)
        shape('outline',(218,167,59,23),3)
        text('visibility',s.visibility,159,171,61,18,'row',0,'visibility')
        text('visibility_other','PUBLIC' if s.visibility=='PRIVATE' else 'PRIVATE',229,173,58,15,'row',3)
        text('room_name',"Logan's game",148,209,173,19,'row',4,'room-name')
        text('edit_room','$MENU_ACCEPT Edit',332,216,39,18,'body',4,'room-name')
        text('room_hint','Shown in Browse games when public',148,230,210,16,'body',3)
        text('campaign',s.campaign,164,258,204,20,'row',4,'campaign')
        text('save','Save 3 - Mansion - Level 12 - 10:42',164,278,200,16,'body',3)
        for y,color in ((266,5),(313,3)):
            shape('triangle',(148,y,7,10),color,direction='left')
            shape('triangle',(360,y,7,10),color,direction='right')
        shape('slash',(31,248,4,45),5)
        text('drop_in','ON' if s.drop_in else 'OFF',164,305,198,18,'row',4,'drop-in')
        text('drop_hint','Friends join at the next area',164,324,210,15,'body',3)
        button('open_room','$MENU_OK OPEN THE ROOM',(43,380,337,31),'open-room',primary=True)
        text('open_hint','Party lobby next',274,390,91,17,'label',2)
        items[-1]['align']='right'
        panel('preview_header','YOUR ROOM',(398,133,199,178))
        text('preview_name',"Logan's game",415,167,120,21,'row')
        shape('outline',(533,168,46,14),3)
        text('preview_visibility',s.visibility,539,170,49,14,'label',3)
        text('preview_save','Load: Mansion, Save 3' if s.campaign.startswith('LOAD') else 'New campaign - Normal',415,194,175,17)
        text('preview_drop','Drop-in at the next area' if s.drop_in else 'Drop-in off',415,210,175,17)
        text('preview_slots','Up to 4 players',415,226,175,17)
        text('room_code_label','ROOM CODE',415,247,175,14,'label',3)
        for i in range(8):
            shape('dashed',(415+i*19.5+(13 if i>=4 else 0),260,16,22),3)
        text('room_code','-',494,260,10,22,'row',3)
        text('code_pending','Appears as soon as the room opens',415,289,175,16,'body',3)
        text('privacy1','Private: only people with your code can join.',398,336,199,16,'body',3)
        text('privacy2','Public: listed in Browse games, where players',398,352,199,16,'body',3)
        text('privacy3',"can see each other's internet address.",398,368,199,16,'body',3)
        screen['selection']=(44,248,334,45)
        screen['focus']='campaign'
    elif name=='lc_code':
        for i in range(8):
            x=107+i*51.5+(20 if i>=4 else 0)
            shape('cell' if i<=len(s.code) else 'dashed',(x,130,45.5,54),1,outline=5 if i==len(s.code) else 3)
            if i==len(s.code):
                shape('rect',(x,130,45.5,2),5)
                shape('rect',(x,172,45.5,12),5)
            text('cell'+str(i),s.code[i] if i<len(s.code) else '',x+1,139,43.5,39,'title')
            items[-1]['align']='center'
        text('dash','-',313,144,18,32,'title',3)
        for i,c in enumerate(ALPHABET+'<'):
            row,col=divmod(i,8)
            button('key_'+str(i),'' if c=='<' else c,(81+col*49.8,205+row*38.2,44.5,33), 'delete' if c=='<' else 'code:'+c)
            if c=='<': shape('backspace',(445.5,329.5,12,9),4)
        for i,(key,label,intent) in enumerate((('paste','$MENU_NEXT PASTE','paste'),('clear','$MENU_OTHER CLEAR','clear'),('done','$MENU_OK DONE','done'))):
            button(key,label,(483,205+i*51,76,46),intent, key!='done' or len(s.code)==8)
        text('alphabet_hint','Codes never contain zero, one, or the letters O, I and L. Keyboard: just type it, or paste with Ctrl+V.',119,366,440,16,'body',3)
        panel('code_status_header','',(81,387,478,34))
        if s.error: shape('rect',(81,387,478,2),7)
        shape('diamond',(99,400,7,6),7 if s.error else 3)
        count={1:'One',2:'Two',3:'Three',4:'Four',5:'Five',6:'Six',7:'Seven',8:'Eight'}.get(8-len(s.code),'')
        text('code_status',s.error or ('Code resolved (fixture only).' if len(s.code)==8 else count+' more characters, then the code is looked up automatically.'),111,397,430,18,'body',7 if s.error else 4)
        screen['focus']='key_10'
    else:
        panel('list_header','PUBLIC GAMES - '+str(len(s.rooms)),(43,130,554,264))
        text('age','Updated 4 s ago',471,137,69,14,'label',3)
        shape('rect',(546,139,40,4),0)
        shape('rect',(546,139,16,4),5)
        for i,label in enumerate(('ROOM','HOST','AREA','PLAYERS','STATUS','PING','BUILD')):
            x,w=COLUMNS[i]; text('column'+str(i),label,x,160,w,14,'label',3)
        for row in range(7):
            y=178+31*row; idx=s.offset+row
            record=s.rooms[idx] if idx<len(s.rooms) else None
            shape('rect',(44,y+29,552,1),3,dim=True)
            if record:
                disabled=record['players']==4 or not record['same'] or record['stale']
                vals=(record['name'],record['host'],record['area'],str(record['players'])+'/4',record['status'],'--','SAME' if record['same'] else 'OTHER')
            else: disabled=True; vals=('','','','','','','')
            for col,(value,(x,w),cap) in enumerate(zip(vals,COLUMNS,(24,12,17,5,13,9,5))):
                status=record['status'] if record else ''
                color=3 if col==5 else (6 if col==6 or (col==4 and status=='In lobby') else 5 if col==4 and status=='Loading' else 7 if col==4 and status=='Full' else 4)
                if col==6 and record and not record['same']: color=7
                tx=x+13 if col==5 else x+13 if col==4 else x
                tw=w-17 if col in (4,5) else w-4
                text('room_'+str(row)+'_'+str(col),field(value,cap),tx,y+7,tw,20,'row' if col in (0,1,2,3) else 'body',color,
                     'select:'+str(row) if record else '', record is not None)
                items[-1]['dim']=disabled
            if record:
                status_color=7 if record['status']=='Full' else 5 if record['status']=='Loading' else 6 if record['status']=='In lobby' else 3
                shape('diamond',(407,y+12,7,6),status_color,dim=disabled)
                shape('outline',(552,y+8,35,14),6 if record['same'] else 7,dim=disabled)
                for bar in range(4):
                    shape('bar',(370+bar*4,y+10,2.5,11),4 if bar<record['players'] else 2,dim=disabled)
                    shape('rect',(483+bar*3,y+20-bar*3,2,3+bar*3),3,dim=True)
        r=s.rooms[s.selected] if s.rooms else None
        text('details_name',field(r['name'],24).upper() if r else '',43,405,85,20,'label',5)
        text('details','New campaign - Act 1 - Normal - Drop-in at the next area - Same release token' if r else 'No public games right now. Host a game or go Back.',128 if r else 43,405,469 if r else 554,20,'body',4 if r else 3)
        text('scroll','Next page',540,425,57,14,'label',3,'page:1')
        text('scroll_up','Previous page',460,425,77,14,'label',3,'page:-1')
        screen['focus']='room_'+str(s.selected-s.offset)+'_0' if r else 'prompt_refresh'
        screen['selection']=(44,178+31*(s.selected-s.offset),552,29) if r else None
    shape('rect',(0,441,640,39),0)
    prompts={'lc_online':[('select','Select','open:lc_host'),('back','Back','back'),('name','Change name','name'),('rejoin','Rejoin','rejoin')],
             'lc_host':[('select','Select','open-room'),('change','Change','campaign'),('open','Open the room','open-room'),('back','Back','back')],
             'lc_code':[('pick','Pick','done'),('delete','Delete','back'),('paste','Paste','paste'),('clear','Clear','clear')],
             'lc_browse':[('join','Join','join'),('refresh','Refresh','refresh'),('back','Back','back')]}[name]
    positions={'lc_online':((43,59),(106,56),(164,92),(259,64)),
               'lc_host':((43,59),(106,66),(175,97),(274,65)),
               'lc_code':((43,50),(98,60),(162,58),(223,59)),
               'lc_browse':((43,50),(98,68),(168,58))}[name]
    for i,(key,label,intent) in enumerate(prompts):
        px,pw=positions[i]
        text('desctext'+str(i+1),PROMPT_TOKENS.get(key,'$MENU_ACCEPT')+' '+label,px,454,pw,17,'body',4,intent)
        items[-1]['prompt_key']=key
    # CMenu refreshes all five standard description slots on a focus change.
    # Give even unused slots real anchors so refresh never targets a missing item.
    for i in range(len(prompts),5): text('desctext'+str(i+1),'',43,454,1,17)
    text('breadcrumb','Main menu > Online' if name=='lc_online' else 'Online > '+{'lc_host':'Host a game','lc_code':'Join by code','lc_browse':'Browse games'}[name],425,455,172,15,'label',3)
    items[-1]['align']='right'
    if name!='lc_code':
        if s.error: shape('panel',(43,411,400,28),1)
        text('inline_error',field(s.error,90),48,415,390,20,'body',7,'dismiss' if s.error else '')
    # Every focusable item participates in one deterministic vertical cycle.
    focus=[e for e in items if e['intent'] and e['enabled']]
    for i,e in enumerate(focus):
        e.update(up=focus[(i-1)%len(focus)]['name'],down=focus[(i+1)%len(focus)]['name'],left=e['name'],right=e['name'])
    if name=='lc_code':
        keys={e['name']:e for e in items if e['name'].startswith('key_')}
        for i in range(32):
            e=keys['key_'+str(i)]; r,c=divmod(i,8)
            e.update(left='key_'+str(r*8+(c-1)%8),right='paste' if c==7 else 'key_'+str(i+1),
                     up='key_'+str(((r-1)%4)*8+c),down='key_'+str(((r+1)%4)*8+c))
        for key,idx in (('paste',7),('clear',15),('done',31)):
            next(e for e in items if e['name']==key)['left']='key_'+str(idx)
    if name=='lc_browse':
        refresh=next(e['name'] for e in items if e.get('prompt_key')=='refresh')
        if not s.rooms: screen['focus']=refresh
        rows={e['name']:e for e in items if e['name'].startswith('room_') and e['intent']}
        for key,e in rows.items():
            _,r,c=key.split('_'); r,c=int(r),int(c)
            e.update(left='room_'+str(r)+'_'+str(max(0,c-1)),right='room_'+str(r)+'_'+str(min(6,c+1)),
                     up='room_'+str(r-1)+'_'+str(c) if r else refresh,
                     down='room_'+str(r+1)+'_'+str(c) if 'room_'+str(r+1)+'_'+str(c) in rows else 'scroll')
    return screen


def layout_problems(screen):
    problems=[]; items=screen['items']; names={e['name'] for e in items}
    if len(names)!=len(items): problems.append('duplicate item')
    for e in items:
        x,y,w,h=e['rect']
        if x<0 or y<0 or w<=0 or h<=0 or x+w>640 or y+h>480: problems.append('unsafe bounds: '+e['name'])
        if e['intent']:
            if e['intent'] not in command_manifest(): problems.append('unknown intent')
            if e['enabled'] and any(e.get(d) not in names for d in ('left','right','up','down')): problems.append('open graph')
    if screen['focus'] not in names: problems.append('missing initial focus')
    return problems


def menu_tree(screen, palette_ids=None):
    palette_ids=palette_ids or {i:str(i) for i in range(8)}
    root=ET.Element('menu',igb=screen['name'],image='textures/menus/'+screen['name'],fullscreen='true',
                    updownonly='false',lighting='false')
    descriptions={e['name']:e for e in screen['items'] if re.fullmatch(r'desctext[1-5]',e['name'])}
    for name,e in descriptions.items():
        # Refresh adds a native dim-colour prefix. A scoped prefix after it keeps
        # the approved foreground while the token still follows the active device.
        root.set(name,'~'+str(palette_ids[4]).zfill(2)+e['text'] if e['text'] else '')
    for e in screen['items']:
        value=e['text']
        if value and (not e['intent'] or e['color']!=4): value='~'+str(palette_ids[e['color']]).zfill(2)+value
        attrs=dict(name=e['name'],type='MENU_ITEM_TEXT',text=value,style='lc_o_'+e['style'],
                   textalignx={'center':'TEXT_ALIGN_CENTER_X','right':'TEXT_ALIGN_RIGHT'}.get(e.get('align'),'TEXT_ALIGN_LEFT'),textaligny='TEXT_ALIGN_TOP',neverfocus=str(not bool(e['intent'])).lower())
        if e['name']==screen['focus']: attrs['startactive']='true'
        if not e['enabled']: attrs.update(enabled='false')
        if e['intent']:
            # Only existing console commands; fixture intent -> item mapping is separate.
            attrs['usecmd']=''  # no unregistered runscript or production operation
            if e['intent'].startswith('open:'): attrs['usecmd']='openmenu '+e['intent'][5:]
            elif e['intent']=='other': attrs['usecmd']=NATIVE_ENTRY
            elif e['intent']=='back' and screen['name']!='lc_code': attrs['usecmd']='openmenu lc_online'
            for d in ('left','right','up','down'):
                if d in e: attrs[d]=e[d]
        item=ET.SubElement(root,'item',attrs)
        if e['intent'] and e['enabled']:
            rect,outline=focus_spec(screen,e)
            target=e['name']+'_focus'
            ET.SubElement(root,'item',name=target,type='MENU_ITEM_MODEL',model='ui/models/model_hide',neverfocus='true',animate='true')
            ET.SubElement(item,'onfocus',item=target,type='focus',model=focus_resource(rect,outline,focus_variant(screen,e)),loop='1')
            ET.SubElement(item,'onfocus',item=target,type='nofocus',model='ui/models/model_hide')
    return root


def tree_problems(root, screen, palette_ids=None):
    errors=layout_problems(screen); items={e.get('name'):e for e in root.findall('item')}
    if root.get('igb')!=screen['name'] or root.get('type'): errors.append('base menu contract')
    expected_root=menu_tree(screen,palette_ids)
    if any(root.get('desctext'+str(i))!=expected_root.get('desctext'+str(i)) for i in range(1,6)):
        errors.append('native description contract')
    for e in screen['items']:
        actual=items.get(e['name'])
        if actual is None: errors.append('missing binding'); continue
        expected=next(i for i in menu_tree(screen,palette_ids) if i.get('name')==e['name'])
        if actual.get('text')!=expected.get('text') or actual.get('style')!='lc_o_'+e['style']: errors.append('text/style contract')
        if e['intent'] and e['enabled']:
            for d in ('left','right','up','down'):
                if actual.get(d)!=e[d]: errors.append('directional graph contract')
        if 'runscript' in actual.get('usecmd',''): errors.append('unregistered production script')
    return errors


def package(root):
    pkg=M.package_for(root)
    ET.SubElement(pkg,'xml',filename='ui/menus/'+root.get('igb'))
    ET.SubElement(pkg,'texture',filename='textures/menus/'+root.get('igb'))
    return pkg


def preview_text(value, device='pad'):
    """Synthetic device fixture, never a substitute for runtime token expansion.

    pad_prompts returns single coloured face-button letters, not round icons.
    Its Start and keyboard labels are bracketed names of the bound controls.
    """
    if device not in ('pad','keyboard'): raise ValueError('unknown preview device')
    labels={'$MENU_ACCEPT':'A','$MENU_BACK':'B','$MENU_NEXT':'Y',
            '$MENU_OTHER':'X','$MENU_OK':'[Start]'} if device=='pad' else {
            '$MENU_ACCEPT':'[Enter]','$MENU_BACK':'[Esc]','$MENU_NEXT':'[Y]',
            '$MENU_OTHER':'[X]','$MENU_OK':'[Enter]'}
    for token,label in labels.items(): value=value.replace(token,label)
    return value


def render(screen, *, size=(1920,1080), fonts=None, text=True, focus=True,
           device='pad', reference_icons=False):
    """Offline preview from the same rectangles/items used to author native assets.

    Nominal Barlow sizes when fonts are provided; no claim of game font rendering.
    Geometry uses only the eight palette entries; dimming is alpha compositing.
    """
    from PIL import Image, ImageDraw, ImageFont
    scale=2.25
    picture=Image.new('RGBA',(1440,1080),'#'+PALETTE[0]); draw=ImageDraw.Draw(picture)
    top=bytes.fromhex(PALETTE[1]); bottom=bytes.fromhex(PALETTE[0])
    for y in range(1080):
        a=(1-y/1080)*.75
        draw.line((0,y,1440,y),fill=tuple(round(a*t+(1-a)*b) for t,b in zip(top,bottom)))
    def rect(box): return tuple(round(v*scale) for v in box)
    def paint(shape):
        x,y,w,h=shape['rect']; coords=rect((x,y,x+w,y+h))
        color=tuple(bytes.fromhex(PALETTE[shape['color']]))+(int(255*(.45 if shape.get('dim') else .92 if shape['color']==1 else 1)),)
        overlay=Image.new('RGBA',picture.size); pen=ImageDraw.Draw(overlay)
        edge=tuple(bytes.fromhex(PALETTE[shape.get('outline',3)]))+(int(255*(1 if shape.get('outline')==5 else .45)),)
        if shape['kind']=='bar':
            pen.polygon([rect((x+min(6,w*.2),y)),rect((x+w,y)),rect((x+w-min(6,w*.2),y+h)),rect((x,y+h))],fill=color)
        elif shape['kind']=='slash':
            pen.polygon([rect((x+2.5,y)),rect((x+w+2.5,y)),rect((x+w,y+h)),rect((x,y+h))],fill=color)
        elif shape['kind']=='triangle':
            pen.polygon([rect((x+w if shape.get('direction')=='left' else x,y)),rect((x if shape.get('direction')=='left' else x+w,y+h/2)),rect((x+w if shape.get('direction')=='left' else x,y+h))],fill=color)
        elif shape['kind']=='backspace':
            pen.line([rect((x+w,y)),rect((x+w,y+h)),rect((x+w*.3,y+h)),rect((x,y+h/2)),rect((x+w*.3,y)),rect((x+w,y))],fill=color,width=3)
            for a,b in (((.5,.25),(.8,.75)),((.8,.25),(.5,.75))):
                pen.line([rect((x+a[0]*w,y+a[1]*h)),rect((x+b[0]*w,y+b[1]*h))],fill=color,width=2)
        elif shape['kind']=='diamond':
            pen.polygon([rect((x+w/2,y)),rect((x+w,y+h/2)),rect((x+w/2,y+h)),rect((x,y+h/2))],fill=color)
        elif shape['kind']=='notch': pen.polygon([rect((x,y)),rect((x+w,y)),rect((x,y+h))],fill=color)
        elif shape['kind']=='dashed':
            for lo,hi in (((x,y),(x+w,y)),((x,y+h),(x+w,y+h)),((x,y),(x,y+h)),((x+w,y),(x+w,y+h))):
                length=abs(hi[0]-lo[0])+abs(hi[1]-lo[1])
                for offset in range(0,round(length),4):
                    a=offset/length;b=min(offset+2.5,length)/length
                    pen.line([rect(tuple(lo[k]+a*(hi[k]-lo[k]) for k in (0,1))),rect(tuple(lo[k]+b*(hi[k]-lo[k]) for k in (0,1)))],fill=edge,width=2)
        else:
            if shape['kind']=='outline': edge=tuple(bytes.fromhex(PALETTE[shape['color']]))+(int(255*(.45 if shape.get('dim') else 1)),)
            pen.rectangle(coords,fill=None if shape['kind']=='outline' else color,outline=edge if shape['kind'] in ('panel','cell','outline') else None,width=2)
        picture.alpha_composite(overlay)
    # Original low-contrast diagonals and dots remain beneath screen panels.
    draw.polygon([rect((295,480)),rect((503,0)),rect((640,0)),rect((433,480))],fill='#'+PALETTE[1])
    watermark=Image.new('RGBA',picture.size); waterpen=ImageDraw.Draw(watermark)
    # Original outlined lettering; no font, logo or game artwork in the texture.
    outlines=[[(0,0),(32,0),(32,78),(0,78),(0,0)],[(42,78),(42,0),(74,78),(74,0)],
              [(85,0),(85,78),(116,78)],[(128,0),(128,78)],
              [(140,78),(140,0),(172,78),(172,0)],[(215,0),(183,0),(183,78),(215,78)],
              [(183,39),(207,39)]]
    for path in outlines:
        waterpen.line([rect((330+u*1.6+(78-v)*.3,320+v*1.2)) for u,v in path],fill=tuple(bytes.fromhex(PALETTE[3]))+(23,),width=2,joint='curve')
    if screen['name']=='lc_online': picture.alpha_composite(watermark)
    for y in range(4,202,8):
        for x in range(370,640,6):
            a=.55*max(0,1-y/210)*min(1,(x-350)/100)
            draw.ellipse(rect((x,y,x+1.2,y+1.2)),fill=tuple(round(v*a+b*(1-a)) for v,b in zip(bytes.fromhex(PALETTE[2]),bytes.fromhex(PALETTE[1]))))
    for shape in screen['shapes']: paint(shape)
    selected=next((e for e in screen['items'] if e['name']==screen['focus']),None)
    if focus and selected and not screen.get('selection'):
        x,y,w,h=selected['rect']; (l,b,r,t),_=focus_spec(screen,selected)
        anchor=x+(w/2 if selected.get('align')=='center' else 0)
        paint(dict(kind='rect' if screen['name']=='lc_code' else 'bar',rect=(anchor+l/.8,y-t/.8,(r-l)/.8,(t-b)/.8),color=5))
        if screen['name']=='lc_online': paint(dict(kind='bar',rect=(30,y-6,4,h+9),color=5))
    if focus and screen.get('selection'):
        paint(dict(kind='panel',rect=screen['selection'],color=2,outline=5))
        sx,sy,sw,sh=screen['selection']
        for shape in screen['shapes']:
            x,y,w,h=shape['rect']
            if sx<=x and sy<=y and x+w<=sx+sw and y+h<=sy+sh and (shape['kind'] in ('diamond','outline') or (w<20 and h<20)):
                paint(shape)
    if not text: return picture.convert('RGB').resize(size)
    draw=ImageDraw.Draw(picture)
    cache={}
    for e in screen['items']:
        if not e['text']: continue
        style=e['style']; size_px=round((22 if style=='title' and e['rect'][3]<30 else STYLES[style][1])*scale)
        font_path=(fonts or {}).get(style,'DejaVuSans.ttf')
        key=(font_path,size_px)
        if key not in cache: cache[key]=ImageFont.truetype(font_path,size_px)
        font=cache[key]; x,y,w,h=e['rect']; value=e['text']
        value=preview_text(value,device)
        value=fit_text(value,w*scale,lambda value:draw.textlength(value,font=font))
        if e.get('align')=='center': x+=(w-draw.textlength(value,font=font)/scale)/2
        if e.get('align')=='right': x+=w-draw.textlength(value,font=font)/scale
        color=e['color']
        if focus and selected and (selected is e or e.get('selected_with')==selected['name']) and not screen.get('selection'): color=0
        rgb=tuple(bytes.fromhex(PALETTE[color]))
        if not e['enabled'] or e.get('dim'): rgb=tuple(round(v*.45+bytes.fromhex(PALETTE[0])[i]*.55) for i,v in enumerate(rgb))
        token=re.match(r'\$(MENU_[A-Z]+)',e['text'])
        if reference_icons and device=='pad' and token:
            glyph=preview_text(token.group(),device)
            if glyph=='[Start]': glyph='\u2261'
            diameter=18; cx=x+diameter/2;cy=y+7
            button_color={'A':6,'B':7,'X':3,'Y':5}.get(glyph,3)
            # The final preview is stretched 4:3 -> 16:9. Counter that stretch
            # for a circular target icon; the engine does not yet supply it.
            draw.ellipse(rect((cx-6.7,cy-8.9,cx+6.7,cy+8.9)),fill='#'+PALETTE[button_color])
            glyph_width=draw.textlength(glyph,font=font)/scale
            if glyph=='\u2261':
                for dy in (-3,0,3):draw.line([rect((cx-3.8,cy+dy)),rect((cx+3.8,cy+dy))],fill='#'+PALETTE[0],width=2)
            else:draw.text(rect((cx-glyph_width/2,y)),glyph,font=font,fill='#'+PALETTE[0])
            value=e['text'][len(token.group()):].lstrip(); x+=diameter
        elif device=='pad' and token:
            glyph=preview_text(token.group(),device)
            face={'A':6,'B':7,'X':3,'Y':5}.get(glyph)
            if face is not None:
                draw.text(rect((x,y)),glyph,font=font,fill='#'+PALETTE[face])
                x+=draw.textlength(glyph+' ',font=font)/scale
                value=e['text'][len(token.group()):].lstrip()
        draw.text(rect((x,y+4)) if style=='title' and h>=30 else rect((x,y)),value,font=font,fill=rgb,stroke_width=0,**({'anchor':'lt'} if style=='title' and h>=30 else {}))
    return picture.convert('RGB').resize(size)


def scene_layout(screen):
    """Engine camera's native 512 x 384 coordinates and matching text hit bounds."""
    # Alignment is applied by CText inside the full box. A centre anchor is retained
    # for the code keys; right-aligned text uses the ordinary left box origin.
    layouts={e['name']:(((e['rect'][0]+(e['rect'][2]/2 if e.get('align')=='center' else 0))*.8,-150,(480-e['rect'][1])*.8),
                       ((-e['rect'][2]*.4 if e.get('align')=='center' else 0),-e['rect'][3]*.8,
                        e['rect'][2]*(.4 if e.get('align')=='center' else .8),0)) for e in screen['items']}
    for e in screen['items']:
        if e['intent'] and e['enabled']: layouts[e['name']+'_focus']=layouts[e['name']]
    return layouts


def texture(template, picture, namespace='lc_o_fixture'):
    """Use a checked owned texture container, replacing every mip with original art."""
    import struct
    from . import igb_file as G
    g=G.IgbFile(template); blocks={}
    images=sorted(g.objects_of('igImage'),key=lambda o:-o.get(2)*o.get(3))
    if not images or len({o.get(13) for o in images})!=len(images): raise G.IgbError('texture needs independent mips')
    for i,o in enumerate(images):
        width=max(1,1024>>i); height=max(1,1024>>i)
        blob=picture.resize((width,height)).convert('RGBA').tobytes()
        for slot,value in {2:width,3:height,6:100,7:8,8:8,9:8,10:8,11:7,12:len(blob),19:width*4,20:0}.items():
            if slot not in o.fields: raise G.IgbError('unsupported image schema')
            struct.pack_into('<i',g.buf,o.fields[slot].offset,value)
        if o.get(13) not in g.blocks: raise G.IgbError('missing texture pixels')
        blocks[o.get(13)]=blob
    return namespace_images(g.rebuilt(blocks),namespace)


def font_probe(ctx):
    """Record active mappings and the retail builder-only registration obstruction."""
    maps={name:[dict(e.attrib) for e in ctx.read_out_xmlb('UI/fonts/'+name+'.XMLB')]
          for name in ('fonts_pc','fonts_hd')}
    return dict(maps=maps,counts={name:len(rows) for name,rows in maps.items()},
                indices=sorted({r['index'] for rows in maps.values() for r in rows}),
                exact_font='BLOCKED in retail data: four fixed global slots; menu styles select medium or big only.',
                evidence={'map_loader':'0x5980f0; name table 0x6e4344; four-name loop 0x5981e6..0x59821a',
                          'metrics_loader':'0x596af0; slot stride 0x1c18; 256 glyphs',
                          'styles':'0x5d7cb0: big -> 1, every other font value -> 0 (medium)',
                          'item_renderer':'0x5c61d0: fixed scale 1 at 0x5c636e; scene transform is not a font scale'},
                fallback='Retained classic medium for row/body/label, big for title. Neither is condensed/italic Barlow.',
                preview='Separately supplied OFL Barlow is a reference layout only; no font files or maps are changed.')


def write(ctx):
    """Preflight the entire family before writing any palette, scene or menu."""
    from . import frontend as F
    colors,styles,ids=theme(ctx.read_out_xmlb('Data/colors.XMLB'),ctx.read_out_xmlb('Data/styles.XMLB'))
    original=ctx.x1_path(F.X1_MENU_IGB)
    if original is None: raise ValueError('online authoring needs the owned menu scene')
    source,_=M.convert_scene(original.read_bytes())
    atlas=ctx.base_index.path('Textures/fonts/font_xmen_med.IGB')
    if atlas is None:
        # Native maps own the real texture filename; never assume a particular edition.
        maps=ctx.read_base_xmlb('UI/fonts/fonts_pc.XMLB')
        entry=next(e for e in maps if e.get('index')=='medium' and 'eng' in e.get('language','eng').split(','))
        atlas=ctx.base_index.path('Textures/fonts/'+entry.get('texture')+'.IGB')
    if atlas is None: raise ValueError('owned PC texture container is missing')
    focus_source=ctx.x1_path('ui/hud/dialog.igb')
    if focus_source is None: raise ValueError('owned flat focus topology missing')
    focus_models={}
    metrics=native_metrics(ctx)
    authored_layouts={}
    pending=[]
    for name in MENUS:
        screen=bound_layout(layout(name),metrics); authored_layouts[name]=screen
        tree=menu_tree(screen,ids)
        problems=tree_problems(tree,screen,ids)
        layouts=scene_layout(screen)
        for e in screen['items']:
            if e['intent'] and e['enabled']:
                rect,outline=focus_spec(screen,e)
                resource=focus_resource(rect,outline,focus_variant(screen,e))
                if resource not in focus_models:
                    picture=focus_picture(screen,e,rect) if outline else None
                    focus_models[resource]=focus_model(focus_source.read_bytes(),rect,outline,picture)
        data=author_scene(source,screen)
        problems+=scene_problems(screen,data)
        if problems: raise ValueError('; '.join(problems))
        pending.append((name,tree,data,texture(atlas.read_bytes(),render(screen,text=False,focus=False),name)))
    probe=font_probe(ctx)
    ctx.write_xmlb('Data/colors',colors,source='frontend:bounded online palette')
    ctx.write_xmlb('Data/styles',styles,source='frontend:four scoped online styles')
    for resource,data in focus_models.items():
        ctx.write_bytes(resource+'.IGB',data,source='frontend:original amber focus shape')
    for name,tree,data,pixels in pending:
        ctx.write_xmlb('UI/menus/'+name,tree,('.XMLB','.engb'),source='frontend:online presentation fixture')
        ctx.write_bytes('UI/menus/'+name+'.IGB',data,source='frontend:authored online bindings and camera')
        ctx.write_bytes('Textures/menus/'+name+'.IGB',pixels,source='frontend:original online geometric field')
        ctx.write_xmlb(F.MENU_PKG_DIR+'/'+name,package(tree),('.PKGB',),source='frontend:online resource closure')
    report={'menus':list(MENUS),'colors':len(colors),'styles':len(styles),'palette_ids':ids,'font_probe':probe,
            'fixture_only':True,'production_entry':F.PLAY_ONLINE_CMD,'layouts':authored_layouts,
            'commands':{name:{e['name']:e['intent'] for e in layout(name)['items'] if e['intent']} for name in MENUS},
            'intents':command_manifest()}
    ctx.write_meta('online_menus_detail.json',report)
    return report


def author_scene(source,screen):
    """Author description aliases without colliding with retired source objects."""
    from . import menu_scene as S, igb_file as G
    existing={o.get(2) for o in G.IgbFile(source).objects_of('igTransform')}
    retired={'desctext'+str(i):'lc_o_source_desc'+str(i) for i in range(1,6)
             if 'desctext'+str(i) in existing}
    if retired: source,_=M.rename_aliases(source,retired)
    return S.author_anchors(source,'button1',scene_layout(screen))


def focus_resource(rect, outline=False, variant=''):
    # A small finite family, determined solely by the authored hit rectangle.
    return 'ui/models/lc_o_focus_'+('outline_' if outline else '')+'_'.join(str(round(v*10)) for v in rect)+variant


def focus_model(source, rect, outline=False, picture=None):
    """Fit owned flat topology to an original solid amber slanted focus bar."""
    import struct
    from . import igb_file as G, menu_scene as S
    data,_=M.fit_flat_panel(source,rect,border=1,opaque=True)
    g=G.IgbFile(data); blocks={}
    for o in g.objects_of('igImage'):
        image=picture.resize((1024,128)).convert('RGBA') if picture is not None else None
        blob=image.tobytes() if image is not None else b'\xff'*4
        width,height=image.size if image is not None else (1,1)
        for slot,value in {2:width,3:height,6:100,7:8,8:8,9:8,10:8,11:7,12:len(blob),19:width*4,20:0}.items():
            if slot in o.fields: struct.pack_into('<i',g.buf,o.fields[slot].offset,value)
        blocks[o.get(13)]=blob
    for o in g.objects_of('igMaterialAttr'):
        for slot in (5,6,7):
            if slot in o.fields: g.set_floats(o,slot,(1,1,1,1))
    for o in g.objects_of('igVertexArray1_1'):
        refs=g.ref_list(o.get(2)); vertices=g.block_floats(refs[0]); l,b,r,t=rect
        for i in range(0,len(vertices),3):
            vertices[i]+=(0 if outline or r-l<50 else 4)*(vertices[i+2]-b)/(t-b)
            vertices[i+1]=40  # relative to the anchor; behind text, in front of field
        g.set_block_floats(refs[0],vertices)
        if picture is not None:
            if len(refs)<=11 or refs[11] not in g.blocks: raise G.IgbError('focus image needs UV stream')
            uv=[]
            for i in range(0,len(vertices),3): uv.extend(((vertices[i]-l)/(r-l),(t-vertices[i+2])/(t-b)))
            g.set_block_floats(refs[11],uv)
        if len(refs)>2 and refs[2] in g.blocks:
            color=2 if outline and min(vertices[2::3])>b+.1 and max(vertices[2::3])<t-.1 else 5
            blocks[refs[2]]=(b'\xff'*4 if picture is not None else bytes.fromhex(PALETTE[color]+'FF'))*o.get(3)
    for o in g.objects_of('igAABox'):
        l,b,r,t=rect
        g.set_floats(o,2,(l,40,b));g.set_floats(o,3,(r+4,40,t))
    import hashlib
    image_name='lc_o_focus_'+hashlib.sha256(picture.tobytes()).hexdigest()[:12] if picture is not None else 'lc_o_focus_white'
    return namespace_images(S.static_model(g.rebuilt(blocks)),image_name)



def palette_ids(colors):
    wanted=[]
    for i,h in enumerate(PALETTE):
        wanted.append(tuple(v/255 for v in bytes.fromhex(h))+(.92 if i==1 else 1,))
    ids={}
    for i,value in enumerate(wanted):
        match=next((e for e in colors if all(abs(a-b)<1e-7 for a,b in zip(T.rgba(e.get('value')),value)) and not e.get('pulse')),None)
        if match is None: raise ValueError('online palette colour missing')
        ids[i]=match.get('id')
    return ids



def reserved_budget(colors,styles):
    """Only the complete online family may consume its explicitly reserved slots."""
    if colors is not None and styles is not None and {e.get('name') for e in styles}.issuperset({'lc_o_'+r for r in STYLES}):
        try: palette_ids(colors)
        except ValueError: pass
        else: return (4,4)  # round-1 ceiling: 71 colours, 28 styles
    return (T.COLOR_RESERVE,T.STYLE_RESERVE)



def focus_spec(screen,item):
    x,y,w,h=item['rect']
    if screen['name']=='lc_code' and item['name'].startswith('key_'):
        return (-w*.4-3.2,-(h+3)*.8,w*.4+3.2,4.8),False
    if screen['name']=='lc_host' and item['name']=='campaign':
        return ((43-x)*.8,-(293-y)*.8,(380-x)*.8,(y-248)*.8),True
    if screen['name']=='lc_browse' and item['name'].startswith('room_'):
        row=int(item['name'].split('_')[1]); top=178+31*row
        return ((44-x)*.8,-(top+29-y)*.8,(596-x)*.8,(y-top)*.8),True
    return (-12,-h*.8-2,w*.8+12,5),False


def fit_text(text, width, measure):
    """Ellipsize within one field using the chosen renderer's width measurement."""
    if width<=0: raise ValueError('text field must have positive width')
    if measure(text)<=width: return text
    if measure('...')>width: return ''
    end=len(text)
    while end and measure(text[:end].rstrip()+'...')>width: end-=1
    return text[:end].rstrip()+'...'


def scene_problems(screen,data):
    from . import igb_file as G, frontend as F
    graph=G.IgbFile(data)
    errors=M.placement_problems(data,scene_layout(screen))
    frame=F._scene_frame(graph)
    errors+=frame['problems']
    reachable={o.get(2) for o in frame['transforms'].values()}
    for name in scene_layout(screen):
        aliases=[o for o in graph.objects if o.name in ('igTransform','igHashedUserInfo','igStringValue') and o.get(2)==name]
        if len(aliases)!=3 or {o.name for o in aliases}!={'igTransform','igHashedUserInfo','igStringValue'}:
            errors.append('incomplete scene alias: '+name)
        if name not in reachable: errors.append('unreachable scene binding: '+name)
    return errors


def native_metrics(ctx):
    """Use the retained active English maps, including their paired classic override."""
    mapping=ctx.read_out_xmlb('UI/fonts/fonts_pc.XMLB')
    result={}
    for index in ('medium','big'):
        choices=[e for e in mapping if e.get('index')==index and 'eng' in e.get('language','eng').split(',')]
        if not choices: raise ValueError('active native font map missing '+index)
        root=ctx.read_out_xmlb('UI/fonts/'+choices[-1].get('data')+'.XMLB')
        result[index]={int(e.get('num')):dict(e.attrib) for e in root}
    return result


def bound_layout(screen,metrics):
    """Fit authored native text, not just previews, with the retained font metrics.

    Device tokens are measured by the runtime; do not clip or rewrite them here.
    The exact scoped-font gate remains open; no nominal Barlow width is assumed.
    """
    result=copy.deepcopy(screen)
    for item in result['items']:
        value=item['text']
        if not value or '$MENU_' in value: continue
        glyphs=metrics[STYLES[item['style']][0]]
        def measure(text):
            return sum(float(glyphs.get(ord(c),glyphs.get(63,{'horizadvance':'12'}))['horizadvance']) for c in text)
        item['text']=fit_text(value,item['rect'][2]*.8,measure)
    return result


def namespace_images(data,prefix):
    """Prevent generated containers from aliasing the owned images they reused."""
    import struct
    from . import igb_file as G
    graph=G.IgbFile(data); replacements={}
    for i,image in enumerate(graph.objects_of('igImage')):
        f=image.fields.get(22)
        if f is None or f.type!='igStringMetaField': continue
        raw=(prefix+'_'+str(i)).encode('ascii')+b'\0';raw+=b'\0'*(-len(raw)%4)
        record=bytearray(graph.data[image.offset:image.offset+image.size])
        at=f.offset-image.offset;record[at:at+f.size]=struct.pack('<I',len(raw))+raw
        struct.pack_into('<I',record,4,len(record));replacements[image.ref]=record
    objects=b''.join(replacements.get(o.ref,graph.data[o.offset:o.offset+o.size]) for o in graph.objects)
    head=bytearray(graph.data[:graph._obj_start]);struct.pack_into('<I',head,16,len(objects))
    result=bytes(head)+objects+graph.data[graph._mem_start:]
    G.IgbFile(result)
    return result



def focus_variant(screen,item):
    return '_row'+item['name'].split('_')[1] if screen['name']=='lc_browse' and item['name'].startswith('room_') else ''


def focus_picture(screen,item,rect):
    """Row geometry retains badges/bars/diamonds when its steel fill is selected."""
    l,b,r,t=rect;x,y,_,_=item['rect']
    left,top=x+l/.8,y-t/.8;width,height=(r-l)/.8,(t-b)/.8
    selected=copy.deepcopy(screen);selected['selection']=(left,top,width,height)
    background=render(selected,size=(1920,1080),text=False,focus=True)
    return background.crop((round(left*3),round(top*2.25),round((left+width)*3),round((top+height)*2.25)))
