"""Original online menu authoring and guarded DLL presentation contracts.

The companion DLL owns all network, clipboard, profile and input services.
Commands are constants for its guarded lcOnlineIntent n(i) registration.
Coordinates are the approved 640 x 480 canvas; scene conversion uses 512 x 384.
"""
from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field as dc_field

from . import menu_theme as T, menu_conversion as M, online_fonts as OF

MENUS = ('lc_online', 'lc_host', 'lc_code', 'lc_browse')
NATIVE_ENTRY = 'openmenu online'
ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
PALETTE = ('0A1830','11284A','2A4A78','7FA6D9','EEF3FA','FFCB3D','54D68A','FF6F55')
STYLES = {'title': ('big',37), 'row': ('medium',15), 'body': ('medium',12.5), 'label': ('medium',11)}
COLUMNS = ((59,128),(188,67),(255,93),(348,58),(406,76),(482,78),(560,37))
# Browse row cells kept as hit/focus targets. [4] status and [5] ping are drawn by the row scenes (no DATA cell, no
# focus anchor): the scene anchor budget of one menu is 256 and every cell costs two.
ROW_COLUMNS = (0, 1, 2, 3, 6)
PROMPT_TOKENS = {'back':'$MENU_BACK','delete':'$MENU_BACK','paste':'$MENU_NEXT',
                 'refresh':'$MENU_NEXT','rejoin':'$MENU_NEXT','clear':'$MENU_OTHER',
                 'name':'$MENU_OTHER','change':'$MENU_OTHER','open':'$MENU_OK'}
STYLE_ALIASES = {'compact_title':('title',OF.COMPACT_TITLE_SCALE),
                 'code_cell':('row',OF.CODE_CELL_SCALE),
                 'card_name':('row',18*.8/OF.BASE_SIZES['row'])}

def font_binding(item):
    role=item['style']
    alias=item.get('font_alias') or ('code_cell' if role=='title' and item['name'].startswith('cell') else 'compact_title' if role=='title' and item['rect'][3]<30 else None)
    if alias:
        source,scale=STYLE_ALIASES[alias]
        return source,scale,'lc_o_'+alias
    return role,OF.SCALES[role],'lc_o_'+role


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
        elif intent in ('dismiss','refresh','retry'): self.error=''
        elif intent=='unavailable': self.error='This action is unavailable in this preview.'
        elif intent=='rejoin': self.menu='lc_code'; self.code='K7QN2X9M'; self.phase='resolved fixture'
        elif intent=='name': self.phase='native name intent fixture'
        elif intent=='room-name': self.phase='room name intent fixture'
        elif intent=='other': self.phase='native fallback intent fixture'
        elif intent=='party': self.error='No party yet.'


def command_manifest():
    return tuple(['open:'+m for m in MENUS]+['code:'+c for c in ALPHABET]+
                 ['select:'+str(i) for i in range(7)]+
                 ['delete','back','clear','paste','done','scroll:1','scroll:-1','page:1','page:-1','join','visibility',
                  'campaign','drop-in','open-room','error','dismiss','refresh','retry','unavailable','rejoin','name','room-name','other','party'])


def theme(colors, styles):
    original=ET.Element('colors')
    for i,h in enumerate(PALETTE):
        rgb=[int(h[j:j+2],16)/255 for j in (0,2,4)]
        ET.SubElement(original,'color',value=' '.join(format(v,'.9g') for v in (*rgb,.92 if i==1 else 1)))
    requests=[T.text_style('lc_o_'+name,font='lc_'+name,normal=4 if name!='label' else 3,
                           focus=0,disabled=3,allow=True) for name,(font,_) in STYLES.items()]
    for role,attrs in zip(STYLES,requests):attrs['textscale']=format(OF.SCALES[role],'.9g')
    # The approved screen-name inset already used a 22-unit title in the
    # reference preview. It shares the title slot, with its own style scale.
    for alias,(role,scale) in STYLE_ALIASES.items():
        attrs=T.text_style('lc_o_'+alias,font='lc_'+role,normal=4,focus=0,disabled=3)
        attrs['textscale']=format(scale,'.9g');requests.append(attrs)
    # All eight entries are part of this family, including model/status colours.
    for attrs, pair in zip(requests,((4,3),(5,3),(6,7),(2,1))):
        attrs['color_highlight'],attrs['color_disabled']=pair
    result=T.allocate(colors,styles,original,requests,color_reserve=4,style_reserve=1)
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
        if name=='lc_code' and key=='done':
            # Enter + Done needs three more units than the Start icon label.
            items[-1]['rect']=(x+pad,y+6,w-pad-5,h-9)
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
        # The keyboard's Enter cap is wider than A. Retain the approved left
        # edge, using the remaining interval up to the settings-panel edge.
        text('edit_room','$MENU_ACCEPT Edit',332,216,48,18,'body',4,'room-name')
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
        text('privacy2','Public: listed in Browse games, where players',398,352,200,16,'body',3)
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
                    shape('bar',(374+bar*4,y+10,2.5,11),4 if bar<record['players'] else 2,dim=disabled)
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
            if e['intent'] not in command_manifest() and not (screen.get('lobby') and e['intent'] in
                ('copy','leave-yes','native-start','native-role','native-leave','native-picker')) and not (
                screen.get('party') and (e['intent'] in PARTY_INTENTS or e['intent']=='current' or e['intent'].startswith('native:'))): problems.append('unknown intent')
            if e['enabled'] and any(e.get(d) not in names for d in ('left','right','up','down')): problems.append('open graph')
    if screen['focus'] not in names: problems.append('missing initial focus')
    return problems


def menu_tree(screen, palette_ids=None):
    palette_ids=palette_ids or {i:str(i) for i in range(8)}
    root=ET.Element('menu',igb=screen['name'],image='textures/menus/'+screen['name'],fullscreen='true',
                    updownonly='false',lighting='false')
    if screen.get('runtime') and not screen.get('party'): root.set('menu_cancel',command(6))
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
        attrs['style']=font_binding(e)[2]
        if e.get('hidden'): attrs['hide']='true'
        if e.get('data'): attrs.update(text=e['text'],clamp='true')
        if e.get('variant') and e.get('parts'):
            attrs.update(type='MENU_ITEM_MODEL',model=variant_resource(screen,e))
            attrs.pop('text',None)
        if e['name']==screen['focus']: attrs['startactive']='true'
        if not e['enabled']: attrs.update(enabled='false')
        if e['intent']:
            # Only existing console commands; fixture intent -> item mapping is separate.
            attrs['usecmd']=''  # no unregistered runscript or production operation
            if e['intent'].startswith('open:'): attrs['usecmd']='openmenu '+e['intent'][5:]
            elif e['intent']=='other': attrs['usecmd']=NATIVE_ENTRY
            elif e['intent']=='back' and screen['name']!='lc_code': attrs['usecmd']='openmenu lc_online'
            if screen.get('runtime'): attrs['usecmd']=e['usecmd'] if 'usecmd' in e else command(intent_number(e['intent']))
            for d in ('left','right','up','down'):
                if d in e: attrs[d]=e[d]
        item=ET.SubElement(root,'item',attrs)
        if e['intent'] and (e['enabled'] or screen.get('runtime')):
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
        if actual.get('text')!=expected.get('text') or actual.get('style')!=expected.get('style'): errors.append('text/style contract')
        if e['intent'] and e['enabled']:
            for d in ('left','right','up','down'):
                if actual.get(d)!=e[d]: errors.append('directional graph contract')
        if screen.get('runtime'):
            if actual.get('usecmd','')!=expected.get('usecmd',''): errors.append('DLL command contract')
        elif 'runscript' in actual.get('usecmd',''): errors.append('unregistered production script')
    return errors


def package(root):
    pkg=M.package_for(root)
    ET.SubElement(pkg,'xml',filename='ui/menus/'+(root.get('name') if root.get('type') in ('HOST_MENU','JOIN_MENU') else root.get('igb')))
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
    for shape in screen['shapes']:
        if not shape.get('hidden'): paint(shape)
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
        if not e['text'] or e.get('hidden'): continue
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
    layouts={e['name']:(((e['rect'][0]+(e['rect'][2]/2 if e.get('align')=='center' else 0))*.8,e.get('plane',-150),(480-e['rect'][1])*.8),
                       ((-e['rect'][2]*.4 if e.get('align')=='center' else 0),-e['rect'][3]*.8,
                        e['rect'][2]*(.4 if e.get('align')=='center' else .8),0)) for e in screen['items']}
    for e in screen['items']:
        if e.get('hit_rect'):
            x,y,_,_=e['rect'];hx,hy,hw,hh=e['hit_rect']
            layouts[e['name']]=(layouts[e['name']][0],((hx-x)*.8,-(hy+hh-y)*.8,(hx+hw-x)*.8,(y-hy)*.8))
        if e['intent'] and (e['enabled'] or screen.get('runtime')): layouts[e['name']+'_focus']=layouts[e['name']]
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
                exact_font='Scoped XML2 Fix capability: [Game] LegendsClassicFonts=1; four additional slots and per-style textscale.',
                evidence={'map_loader':'0x5980f0; name table 0x6e4344; four-name loop 0x5981e6..0x59821a',
                          'metrics_loader':'0x596af0; slot stride 0x1c18; 256 glyphs',
                          'styles':'0x5d7cb0: big -> 1, every other font value -> 0 (medium)',
                          'item_renderer':'0x5c61d0: fixed scale 1 at 0x5c636e; scene transform is not a font scale'},
                fallback='Retail interprets unknown private style names as classic medium. The big style name retains slot one.',
                preview='Private OFL Barlow native metrics/atlases; original maps and classic font pairs preserved.')


def write(ctx, *, preview=False):
    """Preflight the entire family before writing any palette, scene or menu."""
    from . import frontend as F
    if not enabled(ctx) and not preview:return {'enabled':False,'production_entry':NATIVE_ENTRY}
    colors,styles,ids=theme(ctx.read_out_xmlb('Data/colors.XMLB'),ctx.read_out_xmlb('Data/styles.XMLB'))
    if not preview:
        from . import fix_ini as FI
        FI.check_online_dll(ctx.out/'dinput.dll',{'Online':{'Menus':'1'},'Game':{'LegendsClassicFonts':'1'},'Limits':{'ScriptFunctions':'1024'}})
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
    focus_models.update(picker_models(focus_source.read_bytes()))
    metrics=OF.metrics()
    authored_layouts={}
    pending=[]
    native_trees={name:ctx.read_base_xmlb('UI/menus/'+name+'.engb') for name in LOBBIES}
    from . import online_party as PT
    rail=party_rail(F.pda_menu_trees(ctx))
    for name in (*MENUS,*LOBBIES,PARTY_MENU):
        if name in MENUS: screen=bound_layout(runtime_layout(name),metrics)
        elif name in LOBBIES: screen=bound_layout(lobby_layout(name),metrics)
        else: screen=bound_layout(PT.party_layout('host',native=rail),metrics)
        authored_layouts[name]=screen
        tree=menu_tree(screen,ids) if name in (*MENUS,PARTY_MENU) else lobby_tree(native_trees[name],screen,ids)
        if name in MENUS: problems=tree_problems(tree,screen,ids)
        elif name==PARTY_MENU: problems=PT.party_problems(tree,screen,rail,ids)
        else: problems=lobby_problems(tree,native_trees[name],screen)
        layouts=scene_layout(screen)
        for e in screen['items']:
            if e.get('variant') and e.get('parts'):
                rect=(0,-e['rect'][3]*.8,e['rect'][2]*.8,0)
                focus_models[variant_resource(screen,e)]=focus_model(focus_source.read_bytes(),rect,True,variant_picture(e))
            if e['intent'] and (e['enabled'] or screen.get('runtime')):
                rect,outline=focus_spec(screen,e)
                resource=focus_resource(rect,outline,focus_variant(screen,e))
                if resource not in focus_models:
                    picture=focus_picture(screen,e,rect) if outline else None
                    focus_models[resource]=focus_model(focus_source.read_bytes(),rect,outline,picture)
        extra={e.get('name'):(((-1000,-150,-1000)),(0,-1,1,0)) for e in tree.findall('item')
               if e.get('name') not in layouts}
        if name in LOBBIES:
            data=author_scene(source,screen,native_lobby_layouts(tree,screen))
        else:data=author_scene(source,screen)
        problems+=scene_problems(screen,data)
        if problems: raise ValueError('; '.join(problems))
        pending.append((name,tree,data,texture(atlas.read_bytes(),render(screen,text=False,focus=False),name)))
    font_details=OF.write(ctx,atlas.read_bytes())
    probe=font_probe(ctx)
    probe['private_fonts']=font_details
    probe['style_aliases']={name:{'font':'lc_'+role,'textscale':scale} for name,(role,scale) in STYLE_ALIASES.items()}
    ctx.write_xmlb('Data/colors',colors,source='frontend:bounded online palette')
    ctx.write_xmlb('Data/styles',styles,source='frontend:four scoped online styles')
    for resource,data in focus_models.items():
        ctx.write_bytes(resource+'.IGB',data,source='frontend:original amber focus shape')
    for name,tree,data,pixels in pending:
        ctx.write_xmlb('UI/menus/'+name,tree,('.XMLB','.engb'),source='frontend:online presentation fixture')
        scene=tree.get('igb')
        ctx.write_bytes('UI/menus/'+scene+'.IGB',data,source='frontend:authored online bindings and camera')
        ctx.write_bytes('Textures/menus/'+scene+'.IGB',pixels,source='frontend:original online geometric field')
        pkg=package(tree)
        if name in LOBBIES:
            native_pkg=ctx.read_base_xmlb(F.MENU_PKG_DIR+'/'+name+'.PKGB')
            if native_pkg is not None:
                have={(e.tag,e.get('filename')) for e in pkg}
                for e in native_pkg:
                    if (e.tag,e.get('filename')) not in have:pkg.append(copy.deepcopy(e))
        ctx.write_xmlb(F.MENU_PKG_DIR+'/'+name,pkg,('.PKGB',),source='frontend:online resource closure')
    if not preview:ctx.write_bytes('Data/lc_online_menus.cap',CAPABILITY,source='frontend:verified DLL menu capability')
    report={'menus':list(MENUS),'colors':len(colors),'styles':len(styles),'palette_ids':ids,'font_probe':probe,
            'fixture_only':True,'enabled':not preview,'production_entry':F.PLAY_ONLINE_CMD,'layouts':authored_layouts,
            'commands':{name:{e['name']:command(intent_number(e['intent'])) for e in runtime_layout(name)['items'] if e['intent']} for name in MENUS},
            'intents':command_manifest()}
    ctx.write_meta('online_menus_detail.json',report)
    return report


def party_rail(pda_halves):
    """The rail's native routes, read from BOTH native PDA localization halves (they must agree)."""
    from . import online_party as PT
    first,second=pda_halves[0],pda_halves[1]
    if first is None or second is None: raise ValueError('native PDA menu halves are missing: the Party rail needs their routes')
    rail=PT.native_rail_commands(first)
    if PT.native_rail_commands(second)!=rail: raise ValueError('native PDA halves disagree on the Party rail routes')
    return rail


def author_scene(source,screen,extra=None):
    """Author description aliases without colliding with retired source objects."""
    from . import menu_scene as S, igb_file as G
    existing={o.get(2) for o in G.IgbFile(source).objects_of('igTransform')}
    layouts={**(extra or {}),**scene_layout(screen)}
    retired={name:'lc_o_source_'+name for name in layouts if name in existing and name!='button1'}
    if retired: source,_=M.rename_aliases(source,retired)
    return S.author_anchors(source,'button1',layouts)


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
        image=picture.convert('RGBA') if picture is not None else None
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
    if colors is not None and styles is not None and {e.get('name') for e in styles}.issuperset({'lc_o_'+r for r in STYLES}|{'lc_o_compact_title','lc_o_code_cell'}):
        try: palette_ids(colors)
        except ValueError: pass
        else: return (4,1 if any(e.get('name')=='lc_o_card_name' for e in styles) else 2)
    return (T.COLOR_RESERVE,T.STYLE_RESERVE)



FLAT_FOCUS = ('lc_leave_yes','lc_leave_cancel','lc_lobby_dismiss','lc_party_leave_yes','lc_party_cancel')


def focus_spec(screen,item):
    x,y,w,h=item['rect']
    if item['name'] in FLAT_FOCUS:
        return (0,-h*.8,w*.8,0),False
    if screen.get('party') and item.get('hit_rect'):
        # Rail rows, action bars and kick buttons: the focus fill is exactly the drawn control.
        hx,hy,hw,hh=item['hit_rect']
        return ((hx-x)*.8,-(hy+hh-y)*.8,(hx+hw-x)*.8,(y-hy)*.8),False
    if item['name']=='retry' and item.get('hit_rect'):
        # The Retry bar is part of the error scene: focus replaces exactly that bar, never the message beside it.
        hx,hy,hw,hh=item['hit_rect']
        return ((hx-x)*.8,-(hy+hh-y)*.8,(hx+hw-x)*.8,(y-hy)*.8),False
    if screen['name']=='lc_code' and item['name'].startswith('key_'):
        return (-w*.4-3.2,-(h+3)*.8,w*.4+3.2,4.8),False
    if screen['name']=='lc_host' and item['name']=='campaign':
        return ((43-x)*.8,-(293-y)*.8,(380-x)*.8,(y-248)*.8),True
    if screen['name']=='lc_browse' and item['name'].startswith('room_'):
        row=int(item['name'].split('_')[1]); top=178+31*row
        return ((44-x)*.8,-(top+29-y)*.8,(596-x)*.8,(y-top)*.8),True
    if screen.get('lobby') and screen['name']=='join' and item['name']=='text_leaveroom':
        hx,hy,hw,hh=item['hit_rect']
        return ((hx-x)*.8,-(hy+hh-y)*.8,(hx+hw-x)*.8,(y-hy)*.8),True
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
    """Use the private metric tables paired with our scoped font slots."""
    result={}
    for role in STYLES:
        root=ctx.read_out_xmlb('UI/fonts/lc_online_'+role+'.XMLB')
        if root is None: raise ValueError('missing private font metrics: '+role)
        result['lc_'+role]={int(e.get('num')):dict(e.attrib) for e in root}
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
        role,scale,_=font_binding(item);private='lc_'+role in metrics
        glyphs=metrics['lc_'+role if private else STYLES[item['style']][0]]
        if not private:scale=1
        def measure(text):
            return sum(float(glyphs.get(ord(c),glyphs.get(63,{'horizadvance':'12'}))['horizadvance']) for c in text)*scale
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


# These probes describe additive APIs, not release or gameplay identities. Each
# must be present in ONE supplied DLL; separate menu/font DLLs cannot be stacked.
DLL_PROBES = (b'lc-online-menus/1\n', b'lc-online-input/1', b'lc-online-lobby/1', b'lc-online-broker/2', b'lc-online-native/1', b'lc-online-party/1', b'lc-online-errors/1',
              b'lcOnlineIntent\0', 'Online\0'.encode('utf-16le'),
              'Menus\0'.encode('utf-16le'), 'LegendsClassicFonts\0'.encode('utf-16le'),
              b'ui/fonts/lc_fonts_pc.xmlb\0', b'ui/fonts/lc_fonts_hd.xmlb\0',
              b'lc_title\0', b'lc_row\0', b'lc_body\0', b'lc_label\0')
CAPABILITY = b'lc-online-menus/1\n'
LOBBIES = ('host', 'join')
# Round 15 lobby inline copy. Error variants carry the cause (Copy vs Kick target); the toast's first line is the DATA name.
LOBBY_ERROR_COPY = {'copy': 'Could not copy the code. Read it out instead.', 'target': 'Pick another player to kick. Not yourself.'}
LOBBY_TOAST_COPY = 'left or lost connection. The party continues; they can rejoin with the code.'
LOBBY_SERVICE_LOST_COPY = 'Online service lost. Players here stay connected; new players cannot join.'
# The 0.6 host-left panel on the Hub (07-host-left with only the INGAME-DESIGN section 5 variants): body, capsule, buttons.
HOST_LEFT_COPY = {'title': 'THE HOST LEFT',
                  'body1': 'The host disconnected. Host again to continue',
                  'body2': 'from a save on this PC.',
                  'capsule': 'LOCAL SAVE', 'capsule_line': 'Choose a saved campaign when you host again',
                  'again': 'HOST AGAIN', 'back': 'BACK TO ONLINE'}
NOTICE_TEXT = {
    'lc_inline_error': 'This action could not be completed. No room was joined.',
    'lc_notice_unavailable': 'Unavailable in this preview. Use Other ways to play.',
    'lc_notice_resolving': 'Looking up room code...',
    'lc_notice_fixture': 'Online service not connected. No room was joined.',
    'lc_notice_paste_invalid': 'No code on the clipboard. Copy the 8-symbol code first.',
    'lc_notice_code_invalid': 'Use code symbols only. Do not use 0/O or 1/I/L.',
    'lc_notice_name_invalid': 'Use 1 to 31 printable characters for your screen name.',
    'lc_notice_profile_save': 'Name changed. Profile save was refused.',
    'lc_notice_name_open': 'Name editor did not open. Please retry.',
    'lc_notice_recent_save': 'Could not remember this game on this PC. Your previous recent game is unchanged.',
    # Round 6 (lc-online-native/1): native Host setup / room-only admission failed; the DLL has already cleaned up.
    'lc_notice_admission': 'Game setup or admission failed. Go Back and try again.',
    # Round 15 (lc-online-errors/1): native step failures name the step; clipboard names its own cause.
    'lc_notice_discovery': "Could not find the host's game. Go Back and try again.",
    'lc_notice_refused': "The host's game refused you. Check build and settings.",
    'lc_notice_refusal_rules': 'Refused. Settings possibly differ:',
    'lc_notice_service_lost': 'Lost the online service during setup. Try again.',
    'lc_notice_timeout': 'Took too long to connect. Go Back and try again.',
    'lc_notice_clipboard': 'Could not open the clipboard. Type the code instead.',
}
DATA_NAMES = {'local_name', 'self_name', 'last_name', 'last_code', 'last_time',
              'code_value', 'code_remaining', *(f'cell{i}' for i in range(8)),
              # Round 5: every field the broker bridge binds is DATA (normal interned text, no gamevar owner).
              'service', 'self_state', 'browse_hint', 'room_name', 'preview_name', 'room_code', 'details_name',
              'details', 'broker_error', 'list_count', 'list_age', 'lc_host_max_players', 'lc_refusal_rules', 'lc_toast_name', *(f'room_{r}_{c}' for r in range(7) for c in (*ROW_COLUMNS, 5))}
# Round 5b: the DLL selects ONE lc_broker_err_<cause> scene per failure (and hides Retry where retrying cannot help),
# one status / pip / build scene and a dim veil per Browse row, a count + age header and a connected-service scene.
# Round 15 completes the table (INGAME-DESIGN 3.3): the first eight keep their broker/2 meaning; the DLL's
# online_menus_rules::error_cause_key / cause_table are the other half of this contract (tests pin both).
ERROR_CAUSES = ('code_not_found', 'room_full', 'version_mismatch', 'rate_limited', 'timeout', 'offline', 'refused', 'generic',
                'pin_mismatch', 'code_expired', 'room_closed', 'test_mode', 'unsupported', 'busy', 'invalid_name')
RETRYABLE_CAUSES = ('rate_limited', 'timeout', 'offline', 'generic', 'room_closed')
# What each cause tells the player to do next (the DLL's next_action; Retry is the only one that is a control).
NEXT_ACTION = {'code_not_found': 'edit_code', 'room_full': 'browse', 'version_mismatch': 'back', 'rate_limited': 'retry',
               'timeout': 'retry', 'offline': 'retry', 'refused': 'back', 'generic': 'retry', 'pin_mismatch': 'back',
               'code_expired': 'edit_code', 'room_closed': 'retry', 'test_mode': 'back', 'unsupported': 'other_ways',
               'busy': 'wait', 'invalid_name': 'back'}
# One word each action's copy must contain, so a cause can never name the wrong next step.
NEXT_WORD = {'retry': ('retry', 'try again'), 'edit_code': ('code',), 'browse': ('another game', 'browse'),
             'back': ('back', 'update', 'check', 'turn it off', 'turn off'), 'other_ways': ('other ways',), 'wait': ('wait',)}
# Localized copy per cause (09-errors wording, in the inline style round 5 chose: one line, names cause + next step).
ERROR_COPY = {
    'code_not_found': 'Code not found. Ask the host for the current code.',
    'room_full': 'That game is full. Try another game or ask for a new code.',
    'version_mismatch': 'Different game version. Update to the same build.',
    'rate_limited': 'Too many requests. Wait a few seconds, then retry.',
    'timeout': 'The online service did not answer. Try again.',
    'offline': "Can't reach the service. Retry; LAN and IP still work.",
    'refused': 'The online service refused this game. Update the game.',
    'generic': 'Online service request failed. Retry or go Back.',
    'pin_mismatch': 'Online service not verified. Check its setting or update.',
    'code_expired': 'That room closed. Ask the host for a new code.',
    'room_closed': 'Not taking players right now. Try again soon.',
    'test_mode': 'TestMode is on, so online play is off. Turn it off.',
    'unsupported': 'Online needs a complete install. Use Other ways to play.',
    'busy': 'The network link is busy. Wait a moment, then repeat.',
    'invalid_name': 'Room name must be 1-32 plain characters. Go Back.',
}
# Failures that are transient limits or waits read amber; the rest are red (09-errors: Full is amber, the rest red).
AMBER_CAUSES = ('room_full', 'room_closed', 'rate_limited', 'busy')
# Causes each screen's own operations can reach (Hub/Host never resolve a code or list rooms).
_HUB_CAUSES = ('rate_limited', 'timeout', 'offline', 'refused', 'generic', 'pin_mismatch', 'test_mode', 'unsupported', 'busy')
BROKER_CAUSES = {'lc_online': _HUB_CAUSES,
                 'lc_host': _HUB_CAUSES + ('invalid_name',),
                 'lc_code': tuple(c for c in ERROR_CAUSES if c != 'invalid_name'),
                 'lc_browse': tuple(c for c in ERROR_CAUSES if c != 'invalid_name')}
STATUS_KINDS = {'lobby': ('In lobby', 6), 'progress': ('In progress', 3), 'closed': ('Closed', 5), 'full': ('Full', 7)}
BUILD_KINDS = {'same': ('SAME', 6), 'other': ('', 7), 'check': ('CHECK', 3)}
# Round 6 (lc-online-native/1): native Host setup and automatic room-only admission. One of these shows (never beside
# lc_broker_room: the DLL selects exactly one) while the native steps run; every one is a hidden text node at the status anchor.
NATIVE_COPY = {
    'lc_native_tunnel': 'Connecting to the host...',
    'lc_native_discovery': "Finding the host's game...",
    'lc_native_admission': 'Requesting admission to the game...',
    'lc_native_posting': 'Opening the game lobby...',
}
NATIVE_SCREENS = {'lc_online': (), 'lc_host': ('lc_native_posting',),
                  'lc_code': ('lc_native_tunnel', 'lc_native_discovery', 'lc_native_admission'),
                  'lc_browse': ('lc_native_tunnel', 'lc_native_discovery', 'lc_native_admission')}
BROKER_STATUS = ('lc_broker_auth', 'lc_broker_list', 'lc_broker_host', 'lc_broker_resolve', 'lc_broker_empty',
                 'lc_broker_stale', 'lc_broker_room', 'lc_broker_cancel', 'lc_broker_offline_room', *NATIVE_COPY)
BROKER_VARIANTS = BROKER_STATUS + tuple('lc_broker_err_' + c for c in ERROR_CAUSES)
# Localized copy of the DLL-selected status variants (docs/online-menus.md); one hideable node each per screen.
BROKER_COPY = {
    'lc_broker_auth': 'Connecting to Online service...',
    'lc_broker_list': 'Finding public games...',
    'lc_broker_host': 'Opening your room...',
    'lc_broker_resolve': 'Looking up room code...',
    'lc_broker_empty': 'No public games right now. Host a game or go Back.',
    'lc_broker_stale': 'Games may be out of date. Refresh to try again.',
    'lc_broker_cancel': 'Canceling or leaving...',
    'lc_broker_offline_room': 'Online service unavailable. Existing connections stay open; new players cannot join.',
    **NATIVE_COPY,
}
# Browse shows it in the list header (one line beside the count), so it is shorter there.
BROWSE_OFFLINE_COPY = 'Service unavailable. No new players can join.'
BROKER_ROOM_COPY = {'lc_code': 'Room found. Editing the code leaves this room.',
                    'lc_host': 'Room open. Native lobby setup is the next step.',
                    'lc_browse': 'Room found. Native lobby setup is the next step.',
                    'lc_online': 'Room open. Native lobby setup is the next step.'}


# Host settings the DLL reads from the native Game Options (docs/online-menus.md, round 6): independent selectors; the
# runtime shows `lc_host_settings_unknown` alone until native setup has produced them. The two-line scenes carry both
# the word and its explanation (a node cannot wrap), so the DLL needs only the one name per state.
HOST_SETTING_COPY = {'lc_host_new': 'NEW CAMPAIGN', 'lc_host_load': 'SAVED CAMPAIGN',
                     'lc_host_campaign': 'Campaign', 'lc_host_danger_room': 'Danger Room',
                     'lc_host_easy': 'Easy', 'lc_host_normal': 'Normal', 'lc_host_hard': 'Hard'}
HOST_UNKNOWN = ('SET IN GAME OPTIONS', 'Choose them when you open the room')
# The effective installed rule-26 policy, read-only: name -> (word, explanation).
HOST_DROP_COPY = {'lc_host_drop_on': ('ON', 'Friends join at the next area'),
                  'lc_host_drop_off': ('OFF', 'No joining once the game starts'),
                  'lc_host_drop_unknown': ('--', 'This build does not report it')}
HOST_FIXTURE_PROSE = ('save', 'drop_hint', 'preview_save', 'preview_drop', 'preview_slots')  # cleared by the DLL; replaced by the nodes above


def broker_copy(name, key):
    if key == 'lc_broker_room': return BROKER_ROOM_COPY[name]
    if key == 'lc_broker_offline_room' and name == 'lc_browse': return BROWSE_OFFLINE_COPY
    return BROKER_COPY[key]


# Screens carrying each variant. The DLL hides/shows by name and tolerates absent nodes; each screen gets exactly
# the states its own operations can reach (Hub never lists/hosts/resolves, only Retry/Cancel/Error).
BROKER_SCREENS = {
    'lc_online': ('lc_broker_auth', 'lc_broker_cancel'),
    'lc_host': ('lc_broker_auth', 'lc_broker_host', 'lc_broker_room', 'lc_broker_cancel', 'lc_broker_offline_room'),
    'lc_code': ('lc_broker_auth', 'lc_broker_resolve', 'lc_broker_room', 'lc_broker_cancel', 'lc_broker_offline_room'),
    'lc_browse': ('lc_broker_auth', 'lc_broker_list', 'lc_broker_resolve', 'lc_broker_empty', 'lc_broker_stale',
                  'lc_broker_room', 'lc_broker_cancel', 'lc_broker_offline_room'),
}
BROKER_SCREENS = {k: v + NATIVE_SCREENS[k] + tuple('lc_broker_err_' + c for c in BROKER_CAUSES[k]) for k, v in BROKER_SCREENS.items()}
INTENTS = {'open:lc_host':2, 'open:lc_code':3, 'open:lc_browse':4, 'other':5,
           'back':6, 'unavailable':7, 'dismiss':8, 'name':9, 'paste':10, 'delete':11,
           'clear':12, 'done':13, 'rejoin':14, 'copy':16, 'leave-yes':17,
           # Round 5 broker lifecycle (lc-online-broker/2). Rows 0..6 are 24..30, see intent_number.
           'refresh':18, 'open-room':19, 'retry':20, 'visibility':21, 'page:-1':22, 'page:1':23, 'join':31}
BROKER_ROW_FIRST, BROKER_ROW_LAST = 24, 30
# Exact allowed screens of the round-5 intents (docs/online-menus.md table); anything else is a contract error.
BROKER_SCOPE = {18:('lc_browse',), 19:('lc_host',), 20:MENUS, 21:('lc_host',), 22:('lc_browse',), 23:('lc_browse',),
                **{n:('lc_browse',) for n in range(24,31)}, 31:('lc_browse',)}


def enabled(ctx):
    return hasattr(ctx,'opt') and ctx.opt('online_menus', 'off') == 'on'


def capability_problems(data):
    return ['missing DLL probe: '+repr(token) for token in DLL_PROBES if token not in data]


# Round 8 (lc-online-party/1): the in-session Party screen. 68 and 70 are reserved; 63..74 exist on lc_party only.
PARTY_MENU = 'lc_party'
PARTY_INTENTS = {'party-resume':63,'party-invite':64,'party-propose':65,'party-leave':66,'party-leave-yes':67,'party-kick-yes':69,
                 **{f'party-kick:{n}':70+n for n in range(1,5)}}
PARTY_INTENT_NUMBERS = tuple(sorted(PARTY_INTENTS.values()))
PUBLIC_INTENTS = (*range(2,15),16,17,*range(18,32),*range(32,63),*PARTY_INTENT_NUMBERS)


def command(number):
    if type(number) is not int or number not in PUBLIC_INTENTS:
        raise ValueError('not a public online intent')
    return f'runscript lcOnlineIntent({number})'


def intent_number(intent):
    if intent.startswith('code:'):
        return 32+ALPHABET.index(intent[5:])
    if intent.startswith('select:') and intent[7:] in tuple('0123456'):
        return BROKER_ROW_FIRST+int(intent[7:])
    if intent in PARTY_INTENTS or intent.startswith('party-kick:'):
        return PARTY_INTENTS[intent]
    return INTENTS.get(intent, 7)


def _entry(name, text, rect, style='body', color=4, intent='', **kw):
    return dict(name=name,text=text,rect=rect,style=style,color=color,intent=intent,enabled=True,**kw)


def _graph(screen):
    # Optional inline buttons stay linked even while hidden/disabled. Native
    # navigation skips them until the DLL enables their own panel.
    focus=[e for e in screen['items'] if e['intent']]
    for i,e in enumerate(focus):
        e.update(up=focus[i-1]['name'],down=focus[(i+1)%len(focus)]['name'],
                 left=focus[i-1]['name'],right=focus[(i+1)%len(focus)]['name'])


def _variant(key, rect, parts, **kw):
    """One individually hideable model scene (all static decoration travels with it)."""
    return _entry(key,'',rect,'body',4,variant=True,parts=parts,hidden=True,**kw)


def _bar(rect, color=5, slant=5, alpha=None):
    part = dict(kind='bar', rect=rect, color=color, slant=slant)
    if alpha is not None: part['alpha'] = alpha
    return part


def _error_variant(name, cause):
    """lc_broker_err_<cause>: warn rule, diamond, the cause's one-line copy and, only where retrying can help, the Retry bar.

    The DLL shows exactly one cause scene and hides `retry` (a separate hit/focus item over the bar) for causes without a
    bar, so a bar is never drawn for a button that is not there. The bar is a slanted amber shape like the native focus."""
    retry_ok = cause in RETRYABLE_CAUSES
    warn = 5 if cause in AMBER_CAUSES else 7
    copy_ = ERROR_COPY[cause]
    if name == 'lc_code':
        rect = (81, 387, 478, 34)
        parts = [dict(kind='rect', rect=(0, 0, 478, 2), color=warn), dict(kind='diamond', rect=(18, 13, 7, 6), color=warn),
                 dict(text=copy_, rect=(30, 9, 350, 18), style='body', color=warn)]
        if retry_ok: parts.append(_bar((408, 8, 62, 18)))
        retry = (489, 395, 62, 18)
    elif name == 'lc_browse':
        rect = (43, 424, 414, 16)
        if retry_ok:
            parts = [_bar((0, 0, 56, 16)), dict(kind='diamond', rect=(64, 5, 7, 6), color=warn),
                     dict(text=copy_, rect=(78, 1, 295, 15), style='body', color=warn)]
        else:
            parts = [dict(kind='diamond', rect=(2, 5, 7, 6), color=warn), dict(text=copy_, rect=(16, 1, 357, 15), style='body', color=warn)]
        retry = (43, 424, 56, 16)
    else:
        rect = (43, 421, 554, 20)
        parts = [dict(kind='panel', rect=(0, 0, 554, 20), color=1), dict(kind='rect', rect=(0, 0, 3, 20), color=warn),
                 dict(kind='diamond', rect=(12, 7, 7, 6), color=warn), dict(text=copy_, rect=(26, 3, 370, 15), style='body', color=warn)]
        if retry_ok: parts.append(_bar((484, 2, 62, 16)))
        retry = (527, 423, 62, 16)
    return _variant('lc_broker_err_' + cause, rect, parts), retry


def _row_scenes(items):
    """Per-row status diamond+word, player pips + neutral ping bars, build badge and the dim veil for unjoinable rows.

    Models are shared across the seven rows (identical relative art); each row only has its own anchor. They sit between
    the focus fill and the text (plane -170 -> depth -130); the veil sits in front of the text (-200 -> -160)."""
    for r in range(7):
        y = 178 + 31 * r
        for kind, (word, color) in STATUS_KINDS.items():
            items.append(_variant(f'lc_row{r}_st_{kind}', (406, y + 7, 76, 20),
                                  [dict(kind='diamond', rect=(1, 5, 7, 6), color=color),
                                   dict(text=word, rect=(13, 2, 59, 18), style='body', color=color)],
                                  model_name=f'row_st_{kind}', plane=-170))
        for n in range(5):
            parts = [_bar((bar * 5.5, 2, 3, 11), 4, .8) if bar < n else _bar((bar * 5.5, 2, 3, 11), 3, .8, .4) for bar in range(4)]
            # No measured ping exists: four neutral bars, never a number or a colour that implies one.
            parts += [dict(kind='rect', rect=(103 + bar * 3, 12 - bar * 3, 2, 3 + bar * 3), color=3, alpha=.35) for bar in range(4)]
            parts.append(dict(text='--', rect=(121, 0, 24, 15), style='body', color=3))  # the ping value: none measured
            items.append(_variant(f'lc_row{r}_pips_{n}', (374, y + 8, 150, 15), parts, model_name=f'row_pips_{n}', plane=-170))
        for kind, (word, color) in BUILD_KINDS.items():
            parts = [dict(kind='outline', rect=(0, 1, 35, 14), color=color)]
            if word: parts.append(dict(text=word, rect=(8, 1, 27, 14), style='label', color=color))
            items.append(_variant(f'lc_row{r}_build_{kind}', (552, y + 7, 35, 15), parts, model_name=f'row_build_{kind}', plane=-170))
        items.append(_variant(f'lc_row{r}_dim', (44, y, 552, 29), [dict(kind='rect', rect=(0, 0, 552, 29), color=0, alpha=.55)],
                              model_name='row_dim', plane=-200, picture_scale=.05))


def broker_layout(name, screen):
    """Round-5b broker bridge nodes (docs/online-menus.md): status/error scenes, Retry, diagnostic, rows, header, service.

    Everything is authored from constants. No node executes remote text; `broker_error` is DATA only."""
    items=screen['items'];shapes=screen['shapes']
    by={e['name']:e for e in items}
    # The connected-service scene: green diamond + localized word, selected by the DLL (it empties the plain text then).
    if name=='lc_online':
        _host_left_nodes(items)
        items.append(_variant('lc_service_ok',(355,229,120,18),[dict(kind='diamond',rect=(0,3,7,6),color=6),
                              dict(text='Connected',rect=(12,0,100,18),style='row',color=6)],model_name='service_ok'))
    else:
        # 'Room connected' is the longest state the DLL binds; the static diamond implied a connected service.
        by['self_state'].update(rect=(529,46,67,13))
        shapes[:]=[q for q in shapes if not(q['kind']=='diamond' and q['rect']==(529,49,7,6))]
        items.append(_variant('lc_service_ok',(529,46,67,13),[dict(kind='diamond',rect=(0,3,7,6),color=6),
                              dict(text='Connected',rect=(9,0,58,13),style='label',color=6)],model_name='service_ok'))
    status={'lc_online':(48,424,420,16),'lc_host':(48,424,420,16),'lc_code':(111,397,370,18),'lc_browse':(108,425,346,14)}[name]
    offline={'lc_online':(48,408,546,14),'lc_host':(48,408,546,14),'lc_code':(81,424,478,14),'lc_browse':(196,137,258,14)}[name]
    colors={'lc_broker_empty':3,'lc_broker_stale':5,'lc_broker_room':6,'lc_broker_offline_room':7}
    retry=None
    for key in BROKER_SCREENS[name]:
        if key.startswith('lc_broker_err_'):
            variant,retry=_error_variant(name,key[len('lc_broker_err_'):])
            items.append(variant)
            continue
        value=broker_copy(name,key)
        rect=offline if key=='lc_broker_offline_room' else status
        style='label' if key in ('lc_broker_offline_room','lc_broker_stale') else 'body'
        if key=='lc_broker_empty':
            # Empty list: the table frame stays and carries the message (the DLL leaves the detail line empty then).
            rect=(59,187,400,18)
        if key=='lc_broker_stale' and name=='lc_browse':
            # The stale label owns the list-header middle; the DLL never shows it beside the offline-room line.
            rect=(196,137,258,14)
        items.append(_entry(key,value,rect,style,colors.get(key,3),hidden=True))
    # One Retry hit/focus item per screen over the bar the retryable cause scenes draw; the DLL hides it for the others.
    # Its label is the item's own text so it stays in front of the focus bar and takes the native highlight colours.
    e=_entry('retry','RETRY',(retry[0]+13,retry[1]+(retry[3]-12)/2,retry[2]-14,12),'label',0,intent='retry')
    e['enabled']=False;e['hidden']=True;e['hit_rect']=retry;items.append(e)
    diag={'lc_code':(382,399,104,14),'lc_browse':(370,426,85,14)}.get(name,(393,425,128,14))
    items.append(_entry('broker_error','',diag,'label',7,data=True,align='right'))
    if name=='lc_host':
        # Mutually exclusive localized visibility scenes: segment control + the preview badge. Private is the
        # DLL default (it also sets the pair itself when no service is live); the hit item below owns input (intent 21).
        for key in ('visibility','visibility_other','preview_visibility'):
            items.remove(by[key])
        shapes[:]=[q for q in shapes if q['rect'] not in ((148,167,65,23),(218,167,59,23),(533,168,46,14))]
        def scene(public):
            on,off=((70,0,59,23),(0,0,65,23)) if public else ((0,0,65,23),(70,0,59,23))
            labels=(('PUBLIC' if public else 'PRIVATE'),('PRIVATE' if public else 'PUBLIC'))
            return [dict(kind='rect',rect=on,color=4),dict(kind='outline',rect=off,color=3),
                    dict(text='PRIVATE',rect=(11,5,52,16),style='row',color=0 if not public else 3),
                    dict(text='PUBLIC',rect=(81,5,52,16),style='row',color=0 if public else 3),
                    dict(kind='outline',rect=(385,1,46,14),color=3),
                    dict(text='PUBLIC' if public else 'PRIVATE',rect=(391,3,50,14),style='label',color=3)]
        items.append(_variant('lc_host_private',(148,167,431,23),scene(False)));items[-1]['hidden']=False
        items.append(_variant('lc_host_public',(148,167,431,23),scene(True)))
        items.append(_entry('visibility','',(148,167,129,23),'row',4,intent='visibility'))
        # Eight code cells of the round-1 fixture cannot show a DLL string; one DATA field inside one dashed frame can.
        shapes[:]=[q for q in shapes if not(q['kind']=='dashed' and q['rect'][1]==260)]
        shapes.append(dict(kind='dashed',rect=(415,264,175,24),color=3))
        items.remove(by['room_code'])
        items.append(_entry('room_code','---- ----',(421,265,163,22),'title',3,data=True,align='center',intent=''))
        by['open_room'].update(name='open')
        by['edit_room'].update(intent='room-name')
        for e in items:
            if e['name']=='desctext1': e['intent']='unavailable'
            if e['name']=='desctext3': e.update(name='prompt_open',intent='open-room')
        items.append(_entry('desctext3','',(175,455,1,17)))
        _native_host_nodes(screen,by)
    if name=='lc_browse':
        for e in items:
            m=re.fullmatch(r'room_([0-6])_([0-6])',e['name'])
            if m:
                # Every row exists from the start, with its own constant command, disabled until the DLL binds a room.
                e['intent']='select:'+m.group(1);e['enabled']=False;e.pop('dim',None)  # native disabled style, not a baked dim
                # [4] status word and the SAME/CHECK words belong to the row scenes; [6] holds only another build's token.
                if m.group(2)=='6': e['color']=7
            if e['name']=='details_name': e['rect']=(43,405,85,20)
            if e['name']=='details': e['rect']=(128,405,469,20)
            if e['name']=='desctext1': e.update(name='prompt_join',enabled=False)
            if e['name']=='desctext2': e.update(name='prompt_refresh',text='F5 / Y Refresh',rect=(98,455,95,18))
            if e['name']=='desctext3': e['rect']=(200,455,58,18)
        items.append(_entry('desctext1','',(43,455,1,17)))
        items.append(_entry('desctext2','',(98,455,1,17)))
        items[:]=[e for e in items if not re.fullmatch(r'room_[0-6]_[45]',e['name'])]
        # List header: "PUBLIC GAMES" + DATA count ("- N") after it, DLL-ticked "Updated N s ago" at the right with the
        # five-segment refresh bar (the 10 s idle refresh interval); the track is static, the fills are scenes.
        items.remove(by['age'])
        by['list_header']['rect']=(59,137,60,13)
        items.append(_entry('list_count','',(121,137,60,14),'label',4,data=True))
        items.append(_entry('list_age','',(456,137,84,14),'label',3,data=True,align='right'))
        shapes[:]=[q for q in shapes if q['rect']!=(546,139,16,4)]
        for k in range(5):
            items.append(_variant(f'lc_age_fill{k+1}',(546+8*k,139,7,4),[dict(kind='rect',rect=(0,0,7,4),color=5)],model_name='age_fill'))
        _row_scenes(items)
        for row in range(7):
            # Round 7: the measured RTT of the room this PC is in, over the neutral '--' of the row's ping scene (the DLL binds
            # '' for every other row, which leaves the scene's dash alone). DATA only: no focus, no command.
            items.append(_entry(f'room_{row}_5','',(495,178+31*row+8,40,15),'body',4,data=True))
            items.append(_variant(f'lc_row{row}_selected',(44,178+31*row,552,29),
                                  [dict(kind='panel',rect=(0,0,552,29),color=2,outline=5)]))
        screen['focus']='prompt_refresh'


def _host_left_nodes(items):
    """The 0.6 07-host-left panel as a modal Hub scene: red header and rule, the section-5 body, a local-save capsule that
    claims no save, Host again (the Host intent) and Back to Online (dismiss). Never advertises takeover or recovery."""
    c=HOST_LEFT_COPY
    x,y,w,h=96,118,448,214
    # The veil is its own low-resolution scene (alpha only); the card keeps full resolution.
    items.append(_variant('lc_hub_host_left_veil',(0,0,640,480),[dict(kind='rect',rect=(0,0,640,480),color=0,alpha=.88)],
                          model_name='host_left_veil',plane=-200,picture_scale=.05))
    parts=[dict(kind='rect',rect=(0,0,w,h),color=0),dict(kind='rect',rect=(0,0,w,h),color=1),dict(kind='outline',rect=(0,0,w,h),color=2),dict(kind='rect',rect=(0,0,w,3),color=7),
           dict(kind='diamond',rect=(18,22,14,12),color=7),
           dict(text=c['title'],rect=(44,14,380,36),style='title',color=4),
           dict(text=c['body1'],rect=(20,60,408,18),style='body',color=4),
           dict(text=c['body2'],rect=(20,78,408,18),style='body',color=4),
           dict(kind='rect',rect=(20,106,408,52),color=0,alpha=.45),dict(kind='outline',rect=(20,106,408,52),color=2),
           dict(kind='rect',rect=(20,106,3,52),color=5),
           dict(text=c['capsule'],rect=(34,112,380,13),style='label',color=3),
           dict(text=c['capsule_line'],rect=(34,130,380,18),style='row',color=4),
           _bar((20,172,168,31)),_bar((200,172,168,31),2)]
    items.append(_variant('lc_hub_host_left',(x,y,w,h),parts,model_name='host_left',plane=-280))
    for key,label,rect,intent,color in (('lc_hostleft_again',c['again'],(x+20,y+172,168,31),'open:lc_host',0),
                                         ('lc_hostleft_back',c['back'],(x+200,y+172,168,31),'dismiss',4)):
        e=_entry(key,label,(rect[0]+15,rect[1]+6,rect[2]-25,rect[3]-9),'row',color,intent=intent)
        e['enabled']=False;e['hidden']=True;e['hit_rect']=rect;e['plane']=-300;items.append(e)


def _native_host_nodes(screen,by):
    """Round 6 Host setup: settings are chosen in the native Game Options (intent 19 opens them), read back by the DLL and
    shown through hidden localized nodes at the approved anchors. The fixture prose the DLL clears is not authored."""
    items=screen['items']
    items[:]=[e for e in items if e['name'] not in HOST_FIXTURE_PROSE]
    # The CAMPAIGN row is the second way into the native options (the Open button is the first); DROP-IN is read-only.
    by['campaign'].update(text='',intent='open-room')
    by['drop_in'].update(text='',intent='')
    by['open_hint'].update(text='Game options next')
    def node(key,text,rect,style,color,**kw): items.append(_entry(key,text,rect,style,color,hidden=True,**kw))
    items.append(_variant('lc_host_settings_unknown',(164,258,204,36),
        [dict(text=HOST_UNKNOWN[0],rect=(0,0,204,20),style='row',color=3),dict(text=HOST_UNKNOWN[1],rect=(0,20,204,16),style='body',color=3)],
        plane=-170))  # the CAMPAIGN row is the focused one: the scene sits between the focus fill and the text, as the Browse row scenes do
    node('lc_host_new',HOST_SETTING_COPY['lc_host_new'],(164,258,204,20),'row',4)
    node('lc_host_load',HOST_SETTING_COPY['lc_host_load'],(164,258,204,20),'row',4)
    node('lc_host_campaign',HOST_SETTING_COPY['lc_host_campaign'],(164,278,98,16),'body',3)
    node('lc_host_danger_room',HOST_SETTING_COPY['lc_host_danger_room'],(164,278,98,16),'body',3)
    for level in ('easy','normal','hard'): node('lc_host_'+level,HOST_SETTING_COPY['lc_host_'+level],(264,278,100,16),'body',3,align='right')
    for key,(word,why) in HOST_DROP_COPY.items():
        items.append(_variant(key,(164,305,210,34),
            [dict(text=word,rect=(0,0,198,18),style='row',color=3 if key.endswith('unknown') else 4),dict(text=why,rect=(0,19,210,15),style='body',color=3)]))
    # The player count: the DLL binds only the number (DATA); the label is static and sits at the old "Up to N players" line.
    items.append(_entry('lc_host_players_label','MAX PLAYERS',(415,194,92,14),'label',3))
    items.append(_entry('lc_host_max_players','',(512,191,60,18),'row',4,data=True))


def runtime_layout(name,state=None):
    """Production starts with no invented service, room, name or recent record."""
    screen=layout(name,state or Fixture(code='',rooms=[]))
    screen.update(runtime=True,fixture_only=False)
    # Short truthful fallbacks only: the DLL binds the live service/count/room values over these.
    replacements={'local_name':'Player','self_name':'Player','self_initial':'P',
        'self_state':'Not connected','service':'Not connected',
        'browse_hint':'Browse public games','last_name':'','last_code':'',
        'identity':'Installed build: see launcher', 'code_state':'Not connected',
        'code_status':'Type or paste all eight symbols. The code is looked up automatically.',
        'preview_save':'Campaign selection pending',
        'preview_drop':'Friends join at the next area',
        'room_name':'Room name pending','preview_name':'Room pending',
        'save':'No campaign selected','campaign':'SELECT CAMPAIGN',
        'preview_visibility':'PENDING','open_hint':'Creates your room',
        'code_pending':'Share this code with friends','age':'',
        'list_header':'PUBLIC GAMES',
        'details':''}
    for e in screen['items']:
        if e['name'] in replacements: e['text']=replacements[e['name']]
        if e['name'] in DATA_NAMES: e['data']=True
        if e['name'] in ('service','self_state'):e['color']=3
        if e['name'] in ('last_name','last_code'):e['hidden']=True
        if e['name']=='rejoin':e['enabled']=False
        if e['name']=='inline_error': e.update(name='lc_inline_error',text=NOTICE_TEXT['lc_inline_error'],rect=(48,431,546,18),hidden=True)
        if e['intent'] in ('name','paste','clear'):e['enabled']=True
        if name=='lc_code' and e['intent'] in ('paste','clear'):
            # Native keyboard MENU_NEXT/OTHER labels are plain V/C by default;
            # here those keys type symbols. Never advertise them as tools.
            e['text']=('PASTE' if e['name']=='paste' else 'Ctrl+V / Y Paste') if e['intent']=='paste' else (
                'CLEAR' if e['name']=='clear' else 'Shift+Del / X Clear')
    for shape in screen['shapes']:
        if shape['kind']=='diamond' and shape['color']==6:shape['color']=3
        if name=='lc_code' and shape['rect'][1]==130 and shape['rect'][3]==54:
            shape.update(kind='cell',outline=3)
        if name=='lc_code' and shape['rect']==(483,307,76,46):shape['dim']=False
    if name=='lc_code':
        # Only cell text/remaining count is published by input API /1. Neutral
        # cells avoid freezing the round-1 cursor at its initial edit position.
        screen['shapes']=[s for s in screen['shapes'] if not(s['color']==5 and
            s['rect'][1] in (130,172) and s['rect'][2]==45.5)]
    present={e['name'] for e in screen['items']}
    for key,value in NOTICE_TEXT.items():
        if key not in present:
            screen['items'].append(_entry(key,value,(111,397,430,18) if name=='lc_code' else (48,431,546,18),color=7,hidden=True))
    # The rule names a settings refusal gave (DATA, allowlisted, <= 44 characters) follow their static lead-in.
    screen['items'].append(_entry('lc_refusal_rules','',(300,397,242,18) if name=='lc_code' else (237,431,357,18),'body',7,data=True))
    if name=='lc_online':
        screen['items'].append(_entry('lc_recent_empty','No recent game on this PC.',(354,295,225,18),hidden=True))
    if name=='lc_code':
        for e in screen['items']:
            if e['name']=='desctext3':e['rect']=(162,455,85,18)
            if e['name']=='desctext4':e['rect']=(252,455,116,18)
        screen['items'].append(_entry('lc_code_complete','Complete code. Done looks it up again.',(59,219,510,18),hidden=True))
        screen['items'].append(_entry('code_value','',(59,196,250,18),data=True,hidden=True))
        screen['items'].append(_entry('code_remaining','8',(570,219,20,18),data=True,hidden=True))
    broker_layout(name,screen)
    # The old optional generic error anchor was not an input target. All
    # authored Back usecmds are routed by the scoped DLL handler, once.
    _graph(screen)
    if name=='lc_browse':
        # Row cells keep the closed grid (left/right in a row, up/down in a column) while disabled or rebound.
        for e in screen['items']:
            m=re.fullmatch(r'room_([0-6])_([0-6])',e['name'])
            if not m or int(m.group(2)) not in ROW_COLUMNS: continue
            r,c=int(m.group(1)),int(m.group(2))
            i=ROW_COLUMNS.index(c)
            e.update(left=f'room_{r}_{ROW_COLUMNS[max(0,i-1)]}',right=f'room_{r}_{ROW_COLUMNS[min(len(ROW_COLUMNS)-1,i+1)]}',
                     up=f'room_{r-1}_{c}' if r else 'prompt_refresh',down=f'room_{r+1}_{c}' if r<6 else 'scroll')
    if name=='lc_code':
        keys={e['name']:e for e in screen['items'] if e['name'].startswith('key_')}
        for i in range(32):
            r,c=divmod(i,8)
            keys['key_'+str(i)].update(left='key_'+str(r*8+(c-1)%8),
                right='paste' if c==7 else 'key_'+str(i+1),
                up='key_'+str(((r-1)%4)*8+c),down='key_'+str(((r+1)%4)*8+c))
        for key,idx in (('paste',7),('clear',15),('done',31)):
            next(e for e in screen['items'] if e['name']==key)['left']='key_'+str(idx)
    return screen


def runtime_problems(root, screen, palette_ids=None):
    problems=tree_problems(root,screen,palette_ids)
    expected=menu_tree(screen,palette_ids)
    items={e.get('name'):e for e in root.findall('item')}
    if root.get('menu_cancel')!=command(6):problems.append('scoped Back contract')
    for want in expected.findall('item'):
        actual=items.get(want.get('name'))
        if actual is None:
            problems.append('missing runtime item: '+want.get('name'));continue
        for key in ('type','hide','enabled','usecmd','neverfocus','startactive'):
            if actual.get(key)!=want.get(key):problems.append(want.get('name')+': '+key)
        if want.get('name') in DATA_NAMES and any('gamevar' in k.lower() for k in actual.attrib):
            problems.append('competing DATA owner: '+want.get('name'))
    return problems+broker_problems(root,screen)


def _plain(text):
    return re.sub(r'^~\d\d','',text or '')


def broker_problems(root, screen):
    """Contract of the round-5 broker bridge (docs/online-menus.md): intents, scopes, nodes, bindings.

    Checks the serialized tree, not only the layout, so a mutated resource is caught."""
    name=screen['name'];errors=[]
    items={e.get('name'):e for e in root.findall('item')}
    allowed=set(PUBLIC_INTENTS)
    for key,e in items.items():
        cmd=e.get('usecmd','')
        m=re.fullmatch(r'runscript lcOnlineIntent\((\d+)\)',cmd)
        if cmd and not m: errors.append('non-constant command: '+key)
        if not m: continue
        number=int(m.group(1))
        if number not in allowed: errors.append('intent outside the public range: '+key)
        if number in BROKER_SCOPE and name not in BROKER_SCOPE[number]: errors.append(f'intent {number} not allowed on {name}: {key}')
        if number in PARTY_INTENT_NUMBERS and name!=PARTY_MENU: errors.append(f'party intent {number} outside {PARTY_MENU}: {key}')
    def need(key,**attrs):
        e=items.get(key)
        if e is None: errors.append('missing broker node: '+key);return None
        for attr,value in attrs.items():
            if e.get(attr)!=value: errors.append(f'broker node {key}: {attr}={e.get(attr)!r}, expected {value!r}')
        return e
    need('retry',usecmd=command(20),enabled='false',hide='true',type='MENU_ITEM_TEXT')
    e=need('broker_error',clamp='true')
    if e is not None and any('gamevar' in k.lower() for k in e.attrib): errors.append('competing DATA owner: broker_error')
    if 'lc_broker_error' in items: errors.append('the one-size error scene was replaced by per-cause scenes')
    need('lc_service_ok',hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
    for key in BROKER_SCREENS[name]:
        if key.startswith('lc_broker_err_'):
            need(key,hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
            continue
        e=need(key,hide='true',type='MENU_ITEM_TEXT',neverfocus='true')
        if e is not None and _plain(e.get('text'))!=broker_copy(name,key): errors.append('broker copy differs: '+key)
    for key in BROKER_VARIANTS:
        if key not in BROKER_SCREENS[name] and key in items: errors.append('unexpected broker node: '+key)
    for key,e in items.items():
        if 'fixture' in (e.get('text') or '').lower(): errors.append('fixture wording in production asset: '+key)
    if name=='lc_online':
        for key in ('service','browse_hint'): need(key,clamp='true')
        need('lc_hub_host_left',hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
        need('lc_hub_host_left_veil',hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
        need('lc_hostleft_again',usecmd=command(2),enabled='false',hide='true',type='MENU_ITEM_TEXT')
        need('lc_hostleft_back',usecmd=command(8),enabled='false',hide='true',type='MENU_ITEM_TEXT')
    elif 'lc_hub_host_left' in items: errors.append('the host-left panel belongs to the Hub')
    for key in NOTICE_TEXT:
        if key.startswith('lc_notice_') and key not in items: errors.append('missing notice: '+key)
    need('lc_refusal_rules',clamp='true')
    if name in ('lc_host','lc_code','lc_browse'): need('self_state',clamp='true')
    if name=='lc_host':
        need('open',usecmd=command(19));need('prompt_open',usecmd=command(19));need('visibility',usecmd=command(21))
        for key in ('room_name','preview_name','room_code'): need(key,clamp='true')
        need('lc_host_private',type='MENU_ITEM_MODEL');need('lc_host_public',type='MENU_ITEM_MODEL',hide='true')
        if (items.get('lc_host_private') or {}).get('hide')=='true': errors.append('private and public visibility scenes must start exclusive')
        if 'open_room' in items: errors.append('Open item must be named open')
        e=need('campaign',usecmd=command(19),type='MENU_ITEM_TEXT')
        if e is not None and e.get('text') not in ('',None): errors.append('campaign text belongs to the native setting nodes')
        e=need('drop_in',type='MENU_ITEM_TEXT')
        if e is not None and (e.get('usecmd') or e.get('text')): errors.append('drop-in row is read-only and its prose comes from the policy scenes')
        for key in HOST_FIXTURE_PROSE:
            if key in items: errors.append('fixture prose left in the Host asset: '+key)
        for key in HOST_SETTING_COPY:
            e=need(key,hide='true',type='MENU_ITEM_TEXT',neverfocus='true')
            if e is not None and _plain(e.get('text'))!=HOST_SETTING_COPY[key]: errors.append('host setting copy differs: '+key)
        for key in ('lc_host_settings_unknown',*HOST_DROP_COPY): need(key,hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
        e=need('lc_host_max_players',clamp='true',type='MENU_ITEM_TEXT')
        if e is not None and any('gamevar' in k.lower() for k in e.attrib): errors.append('competing DATA owner: lc_host_max_players')
    if name=='lc_browse':
        for r in range(7):
            for c in range(7):
                if c==5:
                    # Round 7: DATA text only (the measured RTT of the joined room), never a cell with focus or a command.
                    need(f'room_{r}_5',clamp='true',neverfocus='true',type='MENU_ITEM_TEXT')
                    if items.get(f'room_{r}_5') is not None and items[f'room_{r}_5'].get('usecmd'): errors.append(f'room_{r}_5 is DATA only')
                    continue
                if c not in ROW_COLUMNS:
                    if f'room_{r}_{c}' in items: errors.append(f'room_{r}_{c} belongs to the row scenes')
                    continue
                e=need(f'room_{r}_{c}',usecmd=command(24+r),enabled='false',clamp='true')
                if e is not None:
                    for d in ('left','right','up','down'):
                        if e.get(d) not in items: errors.append(f'open row graph: room_{r}_{c}')
            need(f'lc_row{r}_selected',hide='true',type='MENU_ITEM_MODEL')
            scenes=[f'lc_row{r}_st_{k}' for k in STATUS_KINDS]+[f'lc_row{r}_pips_{n}' for n in range(5)]+\
                [f'lc_row{r}_build_{k}' for k in BUILD_KINDS]+[f'lc_row{r}_dim']
            for key in scenes: need(key,hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
        for k in range(1,6): need(f'lc_age_fill{k}',hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
        for key in ('list_count','list_age'): need(key,clamp='true')
        need('prompt_join',usecmd=command(31));need('prompt_refresh',usecmd=command(18))
        need('scroll',usecmd=command(23));need('scroll_up',usecmd=command(22))
        for key in ('details_name','details'): need(key,clamp='true')
    return errors


def lobby_layout(role, *, members=1, ready=False, fixture=False, pending=False, picker=False):
    """Approved 05 composition. Native state, not these previews, gates actions."""
    if role not in LOBBIES or not 1<=members<=4: raise ValueError('invalid lobby preview')
    screen={'name':role,'items':[],'shapes':[],'focus':'text_leaveroom',
            'runtime':True,'fixture_only':fixture,'lobby':True}
    if picker:screen['focus']='text_playername1'
    items,shapes=screen['items'],screen['shapes']
    local=1 if role=='host' else min(2,members)
    ready_flags=[n==1 or ready or (n==2 and not pending) for n in range(1,members+1)]
    if role=='join':ready_flags[local-1]=ready
    def text(key,value,rect,style='body',color=4,**kw):
        items.append(_entry(key,value,rect,style,color,**kw));return items[-1]
    def shape(kind,rect,color,**kw):shapes.append(dict(kind=kind,rect=rect,color=color,**kw))
    def variant(key,value,rect,style='label',color=3,visible=False,parts=None):
        return text(key,value,rect,style,color,variant=True,hidden=not visible,parts=parts or [])
    shape('bar',(43,24,55,16),5)
    text('online_tag','ONLINE',(51,26,43,13),'label',0)
    text('brand','LEGENDS CLASSIC',(104,25,270,14),'label',3)
    text('lc_lobby_title','PARTY',(43,45,400,43),'title')
    shape('bar',(43,84,107,4),5)
    shape('panel',(503,24,94,40),1)
    shape('bar',(513,31,20,26),2)
    self_name=('Logan','Kitty','Alex','Sam')[local-1]
    text('lc_self_name',self_name if fixture else '',(540,30,53,15),'row',data=True)
    text('lc_self_initial',self_name[0] if fixture else '',(517,33,17,22),'row',data=True)
    for key,label,color in (('hosting','Hosting',5),('joined','Joined',3),('ready','Ready',6)):
        variant('lc_self_'+key,label,(540,47,53,13),color=color,
                visible=fixture and key==('hosting' if role=='host' else 'ready' if ready else 'joined'))
    shape('panel',(43,109,554,69),1);shape('notch',(43,109,11,11),5)
    text('lc_room_name','Room details pending',(61,127,245,22),'title')
    shape('outline',(315,128,75,16),3)
    text('lc_room_visibility','PENDING',(320,130,65,14),'label',3)
    text('lc_campaign_summary','Campaign pending. Friends join at the next area.',(61,153,375,18),color=3)
    text('lc_code_label','ROOM CODE',(487,118,95,14),'label',3,align='right')
    text('lc_room_code','K7QN-2X9M' if fixture else '---- ----',(452,132,130,23),'title',5,data=True,align='right')
    text('lc_copy_code','Copy code',(486,159,96,16),'label',intent='copy')
    items[-1]['enabled']=fixture
    variant('lc_code_copied','Code copied',(43,356,554,29),'row',6)
    for n in range(1,5):
        x=43+(n-1)*141; y=189; occupied=n<=members
        prefix=f'lc_p{n}_'
        # All card ornaments belong to their individually hideable model. The
        # permanent field contains no occupancy, readiness or build decoration.
        variant(prefix+'card','',(x,y,132,165),visible=fixture and occupied,
                parts=[dict(kind='panel',rect=(0,0,132,165),color=1),dict(kind='rect',rect=(0,0,132,24),color=2)])
        variant(prefix+'selected','',(x,y,132,165),visible=fixture and picker and n==2,
                parts=[dict(kind='outline',rect=(0,0,132,165),color=5,outline=5)])
        for key,value,rect,style,color in (
            ('slot',f'P{n}',(x+10,y+7,35,18),'row',4),
            ('name',('Logan','Kitty','Alex','Sam')[n-1] if fixture else '',(x+10,y+35,112,24),'title',4),
            ('ping',str((38,38,112,65)[n-1]) if fixture and n!=local and not pending else '',(x+26,y+104,40,15),'body',3)):
            e=text(prefix+key,value,rect,style,color,data=True,hidden=not(fixture and occupied))
            if key=='name':e['font_alias']='card_name'
        variant(prefix+'hero_fallback','Hero assigned at start',(x+10,y+57,112,17),'body',3,visible=fixture and occupied)
        variant(prefix+'host','HOST',(x+90,y+6,33,14),color=5,visible=fixture and occupied and n==1 and (role=='host' or members>1))
        isready=ready_flags[n-1] if occupied else False
        variant(prefix+'ready','READY',(x+10,y+86,112,18),'row',6,visible=fixture and occupied and isready)
        variant(prefix+'not_ready','NOT READY',(x+10,y+86,112,18),'row',3,visible=fixture and occupied and not isready)
        variant(prefix+'you','You',(x+10,y+104,112,16),'body',3,visible=fixture and occupied and n==local)
        variant(prefix+'ms','ms',(x+55,y+104,48,16),'body',3,visible=fixture and occupied and n!=local and not pending)
        variant(prefix+'measuring','Measuring',(x+10,y+104,112,16),'body',3,visible=fixture and occupied and n!=local and pending)
        variant(prefix+'same_build','SAME BUILD',(x+10,y+123,100,16),color=6,visible=fixture and occupied and not pending)
        variant(prefix+'checking_build','CHECKING BUILD...',(x+10,y+123,112,16),visible=fixture and occupied and pending)
        # Round 7 (docs/online-party.md section 8): observed facts. Phase/route are DATA (empty = unknown); the badge, the
        # "to host" label and the pending marker are individually hideable scenes the DLL selects.
        variant(prefix+'other_build','OTHER BUILD',(x+10,y+123,100,16),color=7)
        text(prefix+'phase','In lobby' if fixture and occupied else '',(x+10,y+139,112,12),'label',3,data=True)
        text(prefix+'route','direct' if fixture and occupied and n!=local else '',(x+90,y+104,34,16),'label',3,data=True,align='right')
        variant(prefix+'to_host','to host',(x+10,y+150,60,11),'label',3)
        variant(prefix+'pending','',(x,y,132,165),visible=False,parts=[dict(kind='dashed',rect=(0,0,132,165),color=5)])
        variant(prefix+'empty','',(x,y,132,165),visible=fixture and not occupied,
                parts=[dict(kind='outline',rect=(0,0,132,165),color=3)])
        variant(prefix+'empty_title','Waiting for a player',(x+9,y+98,116,20),'row',4,visible=fixture and not occupied)
        variant(prefix+'empty_help','Share the room code',(x+9,y+121,116,17),'body',3,visible=fixture and not occupied)
        variant(prefix+'empty_plus','+',(x+54,y+56,40,35),'title',2,visible=fixture and not occupied)
    count=sum(ready_flags)
    text('lc_ready_count',str(count) if fixture else '',(43,365,8,17),'body',6,data=True)
    text('lc_member_count',str(members) if fixture else '',(66,365,8,17),'body',6,data=True)
    variant('lc_ready_summary','',(53,365,70,17),'body',6,visible=True,
            parts=[dict(text='of',rect=(0,0,15,17),style='body',color=6),
                   dict(text='ready.',rect=(24,0,46,17),style='body',color=6)])
    waiting=members>count
    variant('lc_ready_waiting','Waiting for',(125,365,400,17),'body',3,visible=fixture and waiting,
        parts=[dict(text='to get ready.',rect=(177,0,100,17),style='body',color=3)])
    waiting_row=ready_flags.index(False) if waiting else 0
    text('lc_waiting_name',('Logan','Kitty','Alex','Sam')[waiting_row] if fixture and waiting else '',(193,365,106,17),'body',3,data=True)
    variant('lc_ready_all','All ready. Friends join at the next area.',(125,365,420,17),'body',3,visible=fixture and not waiting and members>1)
    variant('lc_ready_solo','Solo start follows the native minimum-player rule.',(125,365,420,17),'body',3,visible=fixture and members==1 and not waiting)
    for key,label,rect,intent in (
        ('text_startgame','START GAME',(43,391,177,31),'native-start'),
        ('text_kickplayer' if role=='host' else 'text_readygame','KICK PLAYER' if role=='host' else 'READY',(230,391,120,31),'native-role'),
        ('text_leaveroom','LEAVE' if role=='host' else '',(360,391,93,31),'native-leave')):
        if key=='text_startgame' and role!='host':
            text('lc_host_only','HOST ONLY',(rect[0]+15,rect[1]+6,rect[2]-25,rect[3]-9),'row',3)['enabled']=False
            shape('bar',rect,2,dim=True);continue
        # The field is immutable. Native text enabled state and focus supply
        # the changing Start appearance; never bake a guessed roster gate.
        shape('bar',rect,2)
        e=text(key,label,(rect[0]+15,rect[1]+6,rect[2]-25,rect[3]-9),'row',intent=intent,hit_rect=rect)
        if key=='text_startgame':e['enabled']=not fixture or (not waiting and members>1)
    # A single native text item owns each right-bar overlay and its device-aware
    # Back hint. No sibling text survives when the DLL hides that variant.
    variant('lc_guest_leave','$MENU_BACK LEAVE',(365,397,86,22),'row',4,visible=fixture and role=='join' and not ready)
    variant('lc_guest_unready','$MENU_BACK UNREADY',(365,397,86,22),'row',4,visible=fixture and role=='join' and ready)
    text('text_playername1','',(54,224,530,120),'body',intent='native-picker',hidden=not picker)
    items[-1]['plane']=-300
    text('text_readycheck1','',(599,224,20,120),'body',hidden=True)
    for key,value in (('lc_leave_confirm','Leave this game?'),('lc_lobby_error','This action could not be completed.'),
                      ('lc_lobby_error_copy',LOBBY_ERROR_COPY['copy']),('lc_lobby_error_target',LOBBY_ERROR_COPY['target'])):
        variant(key,value,(43,356,554,29),'row',7)
    # Round 15: a guest who left or was lost before the game started (named, six seconds, the party continues) and the
    # service-lost strip (healthy P2P continues; only new players cannot join). Both are inline: Host/Join stays open.
    variant('lc_lobby_guest_left','',(43,356,554,33),'body',7,
            parts=[dict(kind='panel',rect=(0,0,554,33),color=1),dict(kind='rect',rect=(0,0,3,33),color=7),
                   dict(text=LOBBY_TOAST_COPY,rect=(12,17,530,14),style='body',color=3)])
    text('lc_toast_name','',(55,358,300,14),'row',4,data=True)
    items[-1]['plane']=-300
    variant('lc_lobby_service_lost','',(43,427,554,22),'body',7,
            parts=[dict(kind='panel',rect=(0,0,554,22),color=1),dict(kind='rect',rect=(0,0,3,22),color=7),
                   dict(kind='diamond',rect=(12,8,7,6),color=7),
                   dict(text=LOBBY_SERVICE_LOST_COPY,rect=(26,4,520,15),style='body',color=7)])
    for key,label,rect,intent in (
        ('lc_leave_yes','Leave',(400,358,58,24),'leave-yes'),
        ('lc_leave_cancel','Cancel',(466,358,60,24),'dismiss'),
        ('lc_lobby_dismiss','Dismiss',(532,358,65,24),'dismiss')):
        e=text(key,label,rect,'body',intent=intent,hidden=True,plane=-300);e['enabled']=False
    text('desctext1','$MENU_BACK Leave' if role=='host' else '',(324,455,65,18))
    text('desctext2','$MENU_OTHER Kick player' if role=='host' else '$MENU_OTHER Ready / Unready',(106,455,110,18))
    text('desctext3','Copy: Ctrl+C / Y',(221,455,98,18))
    text('desctext4','',(315,455,80,18))
    text('desctext5','$MENU_ACCEPT Select',(43,455,59,18))
    text('breadcrumb','Online > Party',(476,455,121,18),'label',3,align='right')
    # Every ornament travels with the exact named variant the DLL selects.
    # This avoids persistent bars, frames or glyphs from hidden sibling items.
    def child_text(value,rect,style='label',color=3):
        return dict(text=value,rect=rect,style=style,color=color)
    def neutral_bars(x=10,y=108,color=2):
        return [dict(kind='rect',rect=(x+i*4,y+9-height,2.5,height),color=color)
                for i,height in enumerate((3,6,9,12))]
    for e in items:
        key=e['name'];match=re.fullmatch(r'lc_p([1-4])_(.+)',key)
        if match:
            n=int(match.group(1));suffix=match.group(2);x=43+(n-1)*141
            if suffix=='card':e['parts'].append(dict(kind='rect',rect=(10,77,112,.6),color=2))
            if suffix=='selected':
                e.update(rect=(43,189,554,165),plane=-280,parts=[
                    dict(kind='outline',rect=((n-1)*141,0,132,165),color=5),
                    dict(kind='panel',rect=(6,32,542,126),color=1)])
            if suffix in ('ready','not_ready'):
                color=6 if suffix=='ready' else 3
                e.update(rect=(x,189,132,165),text='',parts=[
                    dict(kind='diamond',rect=(11,89,7,6),color=color),
                    child_text('READY' if suffix=='ready' else 'NOT READY',(23,86,100,18),'row',color),
                    dict(kind='rect',rect=(0,161,132,4),color=6 if suffix=='ready' else 2)])
            if suffix in ('host','same_build','checking_build','other_build'):
                w,h=e['rect'][2:];value=e['text'];color=e['color']
                e.update(text='',parts=[dict(kind='outline',rect=(0,0,w,h),color=color),
                    child_text(value,(5,1,w-8,h-1),'label',color)])
            if suffix in ('you','ms','measuring'):
                value=e['text'];positions=(26,104,96,16) if suffix!='ms' else (73,104,39,16)
                e.update(text='',rect=(x,189,132,165),parts=[*neutral_bars(color=6 if suffix=='you' else 2),
                    child_text(value,positions,'body',3)])
            if suffix=='to_host':
                value=e['text'];e.update(text='',parts=[child_text(value,(0,0,60,11),'label',3)])
            if suffix=='empty':e['parts'][0]['kind']='dashed'
            if suffix=='empty_plus':
                e.update(text='',rect=(x+10,224,112,55),parts=[child_text('P'+str(n),(48,0,30,18),'row',3),
                    child_text('+',(42,20,40,35),'title',2)])
        if key.startswith('lc_self_') and e.get('variant'):
            value=e['text'];w,h=e['rect'][2:]
            e.update(text='',parts=[dict(kind='diamond',rect=(0,4,7,5),color=e['color']),
                child_text(value,(10,0,w-10,h),'label',e['color'])])
        if key in ('lc_code_copied','lc_leave_confirm','lc_lobby_error','lc_lobby_error_copy','lc_lobby_error_target'):
            value=e['text'];e.update(text='',plane=-280,parts=[dict(kind='panel',rect=(0,0,554,29),color=1),
                child_text(value,(10,6,340 if key in ('lc_code_copied','lc_leave_confirm','lc_lobby_error') else 470,20),'row',e['color'])])
        if key in ('lc_lobby_guest_left','lc_lobby_service_lost'): e['plane']=-280 if key=='lc_lobby_guest_left' else -170
    _graph(screen)
    # Only offline previews reflect a gate. Authored Start must be available for
    # the native activator/tick to own enabling, and must keep its original flags.
    return screen


def variant_resource(screen,item):
    # Identical relative art (the seven Browse rows' status/pip/build/dim scenes) shares one model across anchors.
    return 'ui/models/lc_o_'+screen['name']+'_'+item.get('model_name',item['name'])


def lobby_tree(original,screen,palette_ids=None):
    """Copy native dependencies and callbacks, replacing only presentation."""
    root=copy.deepcopy(original)
    root.set('igb','lc_lobby_'+screen['name']);root.set('image','textures/menus/lc_lobby_'+screen['name'])
    root.set('updownonly','false');root.set('lighting','false')
    authored=menu_tree(screen,palette_ids)
    existing={e.get('name'):e for e in root.findall('item')}
    by_name={e['name']:e for e in screen['items']}
    actions={'text_startgame','text_readygame','text_kickplayer','text_leaveroom'}
    for e in authored.findall('item'):
        key=e.get('name')
        if key not in existing:root.append(copy.deepcopy(e));continue
        item=existing[key]
        if key in actions:
            # Never change native enabling/visibility, callback or usecmd. The
            # two original actions still accept through their native class.
            for k in ('text','style','textalignx','textaligny','up','down','left','right'):
                if k in e.attrib:item.set(k,e.get(k))
            item.attrib.pop('animtext_scene',None)
            for child in list(item):item.remove(child)
            for child in e:item.append(copy.deepcopy(child))
        elif key in ('text_playername1','text_readycheck1'):
            # LISTBOX draw/row metrics bypass CText's private scale hooks
            # (retail vtable 0x6a062c, draw 0x5c1200, row 0x5c1d00).
            # Retain its native font/measurement contract, not raw 64px glyphs.
            # Native modes select the picker. Keep its LISTBOX backing and
            # list_focus/up/down dependencies exactly as read from the owned tree.
            item.attrib.pop('animtext_scene',None)
            if key=='text_playername1':
                replacements={'list_focus':'ui/models/lc_o_picker_focus',
                              'list_up_arrow':'ui/models/lc_o_picker_up',
                              'list_down_arrow':'ui/models/lc_o_picker_down'}
                for action in item.findall('onfocus'):
                    if action.get('type') in replacements:action.set('model',replacements[action.get('type')])
        else:
            for k in ('text','style','textalignx','textaligny'):
                if k in e.attrib:item.set(k,e.get(k))
    for key,item in existing.items():
        if key not in by_name:
            if item.get('type')=='MENU_ITEM_MODEL':
                item.set('model','ui/models/model_hide')
            # Native data_name/title are still instantiated and updated. Their
            # anchors are retired outside the canvas, not their native items.
    for i in range(1,6):root.set('desctext'+str(i),authored.get('desctext'+str(i),''))
    ET.SubElement(root,'item',name='lc_lobby_v1',type='MENU_ITEM_TEXT',text='',neverfocus='true',hide='true',enabled='false')
    return root


def lobby_problems(root,original,screen):
    errors=layout_problems(screen)
    items={e.get('name'):e for e in root.findall('item')}
    if root.get('type')!=original.get('type'):errors.append('native lobby class')
    presentation={'igb','image','updownonly','lighting',*(f'desctext{i}' for i in range(1,6))}
    for attr,value in original.attrib.items():
        if attr not in presentation and root.get(attr)!=value:errors.append('native root dependency changed: '+attr)
    if len(items)!=len(root.findall('item')):errors.append('duplicate lobby item')
    if 'lc_lobby_v1' not in items:errors.append('missing parsed lobby marker')
    for src in original.findall('item'):
        key=src.get('name');actual=items.get(key)
        if actual is None:errors.append('native dependency missing: '+key);continue
        for attr,value in src.attrib.items():
            if attr in ('callback','usecmd','mode','modes','wait','inputenabled','platform','type') and actual.get(attr)!=value:
                errors.append('native dependency changed: '+key+'/'+attr)
        if key in ('text_playername1','text_readycheck1') and actual.get('type')!='MENU_ITEM_LISTBOX':
            errors.append('real native list required: '+key)
        if key in ('text_playername1','text_readycheck1') and actual.get('style')!=src.get('style'):
            errors.append('native list font/row geometry changed: '+key)
        if key in ('text_startgame','text_readygame','text_kickplayer','text_leaveroom'):
            for attr in ('usecmd','hide','enabled','neverfocus','startactive'):
                if actual.get(attr)!=src.get(attr):errors.append('native action changed: '+key+'/'+attr)
    for e in screen['items']:
        actual=items.get(e['name'])
        if actual is None:errors.append('lobby binding missing: '+e['name']);continue
        if e['name'].startswith('lc_'):
            if e.get('data') and any('gamevar' in k.lower() for k in actual.attrib):errors.append('competing DATA binding')
            if e.get('variant') and e.get('parts') and (actual.get('type')!='MENU_ITEM_MODEL' or actual.get('model')!=variant_resource(screen,e)):
                errors.append('individually hideable variant: '+e['name'])
            if e['intent'] and actual.get('usecmd')!=command(intent_number(e['intent'])):
                errors.append('lobby intent: '+e['name'])
            if e.get('hidden') and actual.get('hide')!='true':errors.append('initial visibility: '+e['name'])
    return errors


def main_hint_layout():
    return {'lc_online_continue':((32,-150,22),(0,-14,440,0))}


def native_lobby_layouts(tree,screen):
    """Retain every parsed native item and place its scroll dependencies safely."""
    layouts=scene_layout(screen)
    for item in tree.findall('item'):
        name=item.get('name')
        if name not in layouts:layouts[name]=((-1000,-150,-1000),(0,-1,1,0))
    for key,y in (('players_up_arrow',225),('players_down_arrow',331)):
        if key in layouts:layouts[key]=((586*.8,-300,(480-y)*.8),(0,-12*.8,9*.8,0))
    return layouts


def picker_models(source):
    """Original list focus/arrow art; native LISTBOX callbacks own visibility."""
    result={}
    selected=_entry('picker','',(0,0,530,25),parts=[dict(kind='panel',rect=(0,0,530,25),color=2,outline=5)])
    result['ui/models/lc_o_picker_focus']=focus_model(source,(0,-20,424,0),True,variant_picture(selected))
    for direction in ('up','down'):
        arrow=_entry('picker_arrow','',(0,0,9,12),parts=[dict(kind='triangle',rect=(0,0,9,12),color=3,direction=direction)])
        result['ui/models/lc_o_picker_'+direction]=focus_model(source,(0,-9.6,7.2,0),True,variant_picture(arrow))
    return result


def output_problems(out):
    """File-level gate before an installer may enable Menus and private fonts."""
    from pathlib import Path
    from .common import decode_xmlb,FileIndex
    out=Path(out);errors=[];index=FileIndex(out)
    marker=index.path('Data/lc_online_menus.cap')
    if marker is None or marker.read_bytes()!=CAPABILITY:errors.append('exact capability marker missing')
    for name in (*MENUS,*LOBBIES,PARTY_MENU):
        scene=name if name in (*MENUS,PARTY_MENU) else 'lc_lobby_'+name
        for rel in [f'UI/menus/{name}.XMLB',f'UI/menus/{name}.engb',f'UI/menus/{scene}.IGB',
                    f'Textures/menus/{scene}.IGB',f'Packages/generated/maps/package/menus/{name}.PKGB']:
            if index.path(rel) is None:errors.append('missing '+rel)
        pkg=index.path(f'Packages/generated/maps/package/menus/{name}.PKGB')
        if pkg is not None:
            try:
                entries=decode_xmlb(pkg.read_bytes())
                for entry in entries:
                    filename=entry.get('filename','')
                    # Package paths are game-relative. Do not follow a corrupt
                    # package out of the build while checking its closure.
                    relative=Path(filename.replace('\\','/'))
                    if not filename or relative.drive or relative.root or '..' in relative.parts:
                        errors.append(name+': unsafe package resource');continue
                    ext='.IGB' if entry.tag.lower() in ('model','texture') else '.XMLB' if entry.tag.lower()=='xml' else None
                    if ext and index.path(filename+ext) is None:errors.append(name+': unresolved '+filename)
            except Exception as error:
                errors.append(name+': invalid package ('+type(error).__name__+')')
    return errors


_GENERATED_FONTS = None


def text_layer(items, *, size=(1440,1080), device='pad'):
    """Transparent native-metric prediction, also used for original model art.

    The renderer consumes the exact generated metrics and pixels. It is an
    offline prediction and does not establish engine clipping or draw order.
    """
    from PIL import Image
    import numpy as np
    global _GENERATED_FONTS
    if _GENERATED_FONTS is None:
        _GENERATED_FONTS={}
        for role in OF.ROLES:
            table,atlas=OF.generate(role)
            _GENERATED_FONTS[role]=(table,atlas,{int(e.get('num')):e.attrib for e in table})
    canvas=Image.new('RGBA',(1440,1080));factor=1080/384
    tokens={'$MENU_ACCEPT':(0x80,0x90),'$MENU_BACK':(0x81,0x91),
            '$MENU_NEXT':(0x83,0xd5),'$MENU_OTHER':(0x82,0xc2),'$MENU_OK':(0x84,0x90)}
    for item in items:
        if not item.get('text') or item.get('hidden'):continue
        value=item['text']
        for token,codes in tokens.items():value=value.replace(token,chr(codes[device=='keyboard']))
        role,scale,_=font_binding(item);table,atlas,glyphs=_GENERATED_FONTS[role]
        x,y,w,h=item['rect'];pen=x*.8*factor;top=y*.8*factor
        measure=lambda s:sum(float(glyphs.get(ord(c),glyphs[63])['horizadvance']) for c in s)*scale
        value=fit_text(value,w*.8,measure)
        width=measure(value)
        if item.get('align')=='center':pen+=(w*.8-width)*factor/2
        if item.get('align')=='right':pen+=(w*.8-width)*factor
        rgb=np.array(tuple(bytes.fromhex(PALETTE[item['color']])),dtype=float)
        if not item.get('enabled',True) or item.get('dim'):rgb=rgb*.45+np.array(tuple(bytes.fromhex(PALETTE[0])))*.55
        for char in value:
            code=ord(char);g=glyphs.get(code,glyphs[63])
            box=tuple(round(float(g[key])*extent-.5) for key,extent in zip(('s','t','s2','t2'),(atlas.width,atlas.height,atlas.width,atlas.height)))
            tile=atlas.crop(box)
            if tile.width and tile.height:
                pixels=np.array(tile)
                if code not in OF.PAD and code not in OF.KEYS:pixels[:,:,:3]=(pixels[:,:,:3].astype(float)*rgb/255).astype('uint8')
                tile=Image.fromarray(pixels).resize((max(1,round(float(g['width'])*factor*scale)),max(1,round(float(g['height'])*factor*scale))),Image.Resampling.BILINEAR)
                canvas.alpha_composite(tile,(round(pen+float(g['horizoffset'])*factor*scale),
                    round(top+(float(table.get('ascender'))-float(g['baseline']))*factor*scale)))
            pen+=float(g['horizadvance'])*scale*factor
    return canvas.resize(size)


def variant_picture(item):
    """One transparent model contains all static children of a hidden scene."""
    from PIL import Image,ImageDraw
    _,_,w,h=item['rect'];scale=item.get('picture_scale',2.25)
    canvas=Image.new('RGBA',(max(1,round(w*scale)),max(1,round(h*scale))))
    pen=ImageDraw.Draw(canvas)
    for part in item.get('parts',[]):
        if 'kind' not in part:continue
        x,y,pw,ph=part['rect'];box=tuple(round(v*scale) for v in (x,y,x+pw,y+ph))
        color='#'+PALETTE[part['color']]
        if part['kind']=='outline':pen.rectangle(box,outline=color,width=2)
        elif part['kind']=='bar':
            # Parallelogram leaning right like the native focus bar (its top edge is shifted right by `slant` units).
            l,t,r,b=box;k=round(part.get('slant',5)*scale)
            if part.get('alpha') is not None: color=tuple(bytes.fromhex(PALETTE[part['color']]))+(round(255*part['alpha']),)
            pen.polygon([(l+k,t),(r,t),(r-k,b),(l,b)],fill=color)
        elif part.get('alpha') is not None and part['kind']=='rect':
            l,t,r,b=box;rgb=tuple(bytes.fromhex(PALETTE[part['color']]))
            pen.rectangle((l,t,r,b),fill=rgb+(round(255*part['alpha']),))
        elif part['kind']=='triangle':
            l,t,r,b=box
            points=((l,b),((l+r)//2,t),(r,b)) if part.get('direction')=='up' else ((l,t),((l+r)//2,b),(r,t))
            pen.polygon(points,fill=color)
        elif part['kind']=='diamond':
            l,t,r,b=box;pen.polygon(((l,(t+b)//2),((l+r)//2,t),(r,(t+b)//2),((l+r)//2,b)),fill=color)
        elif part['kind']=='dashed':
            l,t,r,b=box
            for left,top,right,bottom in ((l,t,r,t),(l,b,r,b),(l,t,l,b),(r,t,r,b)):
                length=max(abs(right-left),abs(bottom-top))
                for offset in range(0,length,9):
                    a=offset/max(1,length);end=min(length,offset+5)/max(1,length)
                    pen.line((round(left+(right-left)*a),round(top+(bottom-top)*a),
                              round(left+(right-left)*end),round(top+(bottom-top)*end)),fill=color,width=2)
        else:pen.rectangle(box,fill=color,outline='#'+PALETTE[part.get('outline',3)] if part['kind']=='panel' else None,width=2)
    text=[]
    if item['text']:text.append({**item,'name':'variant_label','rect':(0,0,w,h),'hidden':False})
    for part in item.get('parts',[]):
        if 'text' in part:text.append(_entry('variant_part',part['text'],part['rect'],part.get('style','body'),part.get('color',4)))
    layer=text_layer(text)
    canvas.alpha_composite(layer.crop((0,0,canvas.width,canvas.height)))
    # Native texture containers accept these bounded power-of-two dimensions.
    def power(n):return min(2048,1<<(n-1).bit_length())
    return canvas.resize((power(canvas.width),power(canvas.height)))


def render_native(screen, *, size=(1920,1080), device='pad', native_picker=None):
    """Same field geometry, generated glyphs and model scenes as the build."""
    screen=copy.deepcopy(screen)
    selected=next((e for e in screen['items'] if e['name']==screen['focus'] and e['enabled'] and not e.get('hidden')),None)
    picture=render(screen,size=(1440,1080),text=False,focus=False).convert('RGBA')
    layers=[];groups={}
    outline=focus_spec(screen,selected)[1] if selected else False
    for order,e in enumerate(screen['items']):
        if e.get('hidden'):continue
        if e.get('variant') and e.get('parts'):
            x,y,w,h=e['rect'];tile=variant_picture(e).resize((round(w*2.25),round(h*2.25)))
            layers.append((e.get('plane',-150)+40,order,'tile',(tile,(round(x*2.25),round(y*2.25)))))
        else:
            if selected and not outline and (e['name']==selected['name'] or e.get('selected_with')==selected['name']):e['color']=0
            groups.setdefault(e.get('plane',-150),[]).append(e)
    for plane,items in groups.items():layers.append((plane,10000,'text',items))
    if selected and selected['name']!='text_playername1':
        (l,b,r,t),_=focus_spec(screen,selected);x,y,_,_=selected['rect']
        anchor=x+(selected['rect'][2]/2 if selected.get('align')=='center' else 0)
        left,top=anchor+l/.8,y-t/.8;width,height=(r-l)/.8,(t-b)/.8
        if selected['name'] in FLAT_FOCUS:
            from PIL import Image
            tile=Image.new('RGBA',(round(width*2.25),round(height*2.25)),'#'+PALETTE[5])
        else:
            focused=copy.deepcopy(screen)
            if outline:focused['selection']=(left,top,width,height)
            tile=render(focused,size=(1440,1080),text=False,focus=True).crop((round(left*2.25),round(top*2.25),round((left+width)*2.25),round((top+height)*2.25))).convert('RGBA')
        layers.append((selected.get('plane',-150)+40,9999,'tile',(tile,(round(left*2.25),round(top*2.25)))))
    if native_picker is not None and any(not e.get('hidden') and re.fullmatch(r'lc_p[1-4]_selected',e['name']) for e in screen['items']):
        layers.append((-300,10001,'picker',None))
    # Predict the authored planes (model vertices sit +40 behind their anchor).
    # Actual font/model depth behavior remains a real-game acceptance gate.
    for _,_,kind,payload in sorted(layers,key=lambda layer:(-layer[0],layer[1])):
        if kind=='tile':picture.alpha_composite(*payload)
        elif kind=='text':picture.alpha_composite(text_layer(payload,device=device))
        else:native_picker(picture,screen)
    return picture.convert('RGB').resize(size)
