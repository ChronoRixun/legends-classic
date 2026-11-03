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
CODE_TOOL_WIDTH = 104  # Space/Enter key label plus DONE, with inner padding
PALETTE = ('0A1830','11284A','2A4A78','7FA6D9','EEF3FA','FFCB3D','54D68A','FF6F55')
STYLES = {'title': ('big',37), 'row': ('medium',15), 'body': ('medium',12.5), 'label': ('medium',11)}
COLUMNS = ((59,128),(188,67),(255,93),(348,58),(406,76),(482,78),(560,37))
# Browse row cells kept as hit/focus targets. [4] status and [5] ping are drawn by the row scenes (no DATA cell).
# The five cells of a row share ONE focus anchor (room_<r>_focus): their focus bar is the whole row anyway.
ROW_COLUMNS = (0, 1, 2, 3, 6)
# Retail has 175 anchors; the atomic co-op installer advertises the expanded tables.
ENGINE_SCENE_ANCHORS = 175
ANCHOR_CAPABILITY = b'menu-anchors/512'


def engine_scene_anchors(dll=b''):
    """Effective capacity of ONE probed companion DLL, with the retail fallback."""
    return 512 if ANCHOR_CAPABILITY in dll else ENGINE_SCENE_ANCHORS


# 060q (round 15 + fix A/B: Browse 184 + 2 backdrop anchors, Host lobby 178 + 2): on a screen listed here every focus
# bar of one plane is carried by ONE model item at that plane's scene origin, its geometry authored at the owner's
# absolute position (the same bar, pixel for pixel). Each focusable item sets the shared item's model on focus and
# normally hides it on nofocus. Code/Browse use gain-only replacement below. XMen2.exe's menu setFocus (base CMenu vt+4 = 0x5aaf80) runs the old item's loss
# (item vt+0x4c(0)) to completion before the new item's gain (vt+0x4c(1)), so a shared target always ends with the new
# item's bar. Saves (focus anchors - planes) per screen. Browse has one plane (-150); the lobbies two (-150, -300).
SHARED_FOCUS_SCREENS = ('lc_code', 'lc_browse', 'host', 'join')
# Retail onfocus storage is 75 records (5af147, 52 bytes each). These pages used 80/82.
# One plane and gain-only replacement needs one record per action, including Retry.
COMPACT_FOCUS_SCREENS = ('lc_code', 'lc_browse')
SHARED_FOCUS = 'lc_focus'
SHARED_FOCUS_ORIGIN = (0, -150, 384)


def shared_focus(plane):
    """(target item name, scene origin) of the shared focus item for one plane."""
    return (SHARED_FOCUS if plane == -150 else f'{SHARED_FOCUS}_{abs(int(plane))}'), (0, plane, 384)
# Approved seven rows require the companion's menu-anchors/512 capability.
BROWSE_ROWS = 7
PROMPT_TOKENS = {'back':'$MENU_BACK','delete':'$MENU_BACK','paste':'$MENU_NEXT',
                 'refresh':'$MENU_NEXT','rejoin':'$MENU_NEXT','clear':'$MENU_OTHER',
                 'name':'$MENU_OTHER','change':'$MENU_OTHER','open':'$MENU_OK'}
# What a pad player sees and presses on the four co-op screens (the designs: X Change name / Clear, Y Rejoin / Paste / Refresh).
# The game binds its menu codes to the play layout, so a pad's own MENU_OTHER is Y and MENU_NEXT is RT; the DLL reads X as OTHER
# and Y as NEXT on these screens and draws the two tokens as those buttons (xml2-fix online_menus_rules.hpp pad_menu_mask /
# pad_prompt_code, 060p live round failure 8). The tokens below therefore name the JOB, not the engine's button: Change name,
# Clear are $MENU_OTHER, Rejoin, Paste and Refresh are $MENU_NEXT (the native lobbies keep the engine's own buttons).
# Keyboard labels stay the engine's own ([Del] / [KP5]).
PAD_TOKEN_BUTTONS = {'$MENU_OTHER':'X','$MENU_NEXT':'Y'}
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
        self.offset = max(0,min(self.offset,max(0,len(self.rooms)-BROWSE_ROWS)))
        if self.selected < self.offset: self.offset=self.selected
        if self.selected >= self.offset+BROWSE_ROWS: self.offset=self.selected-(BROWSE_ROWS-1)

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
            self.offset=max(0,min(self.offset+BROWSE_ROWS*int(intent[5:]),max(0,len(self.rooms)-BROWSE_ROWS)))
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
    # The engine blends a focused item between color_focus and color_highlight; the live round showed
    # focused rows as the 50% mix of navy and amber on the amber bar. Rows keep a steady navy; amber stays
    # allocated through the never-focused title style (the ~ text prefixes need all eight entries).
    # 0.6 preview fix L (060r live failure 7, "pale text on amber"): the body and label styles used to carry green / blue as their
    # highlight, which is what a FOCUSED body / label item blends toward - Cancel, F5 / Y Refresh and the other body prompts read green,
    # Next page and the other labels read pale on the amber bar. Every style a focus bar can sit under now blends navy -> navy
    # (highlight = focus = 0). Green and blue stay allocated through the two never-focused alias styles (the screen-name inset and
    # the lobby card name), which no focus bar ever reaches.
    for attrs, pair in zip(requests,((5,3),(0,3),(0,7),(0,1))):
        attrs['color_highlight'],attrs['color_disabled']=pair
    keep_alive={'lc_o_compact_title':6,'lc_o_card_name':2}
    for attrs in requests:
        if attrs['name'] in keep_alive: attrs['color_highlight']=keep_alive[attrs['name']]
    result=T.allocate(colors,styles,original,requests,color_reserve=4,style_reserve=1)
    if len(result[0])>T.COLOR_LIMIT or len(result[1])>T.STYLE_LIMIT:
        raise ValueError('online family exceeds native capacity')
    return result


# Hub help box copy per focusable row (01-hub: the Host row's is the approved text).
HUB_HELP = {'host': ('HOST A GAME', 'Open a private room and share its code with friends,', 'or list it so anyone can join.'),
            'code': ('JOIN BY CODE', 'Type the 8-character code your host sent you,', 'or paste it. Keyboard, pad and mouse all work.'),
            'browse': ('BROWSE GAMES', 'See the public games that are open right now', 'and join one. Players there see your address.'),
            'other': ('OTHER WAYS TO PLAY', "The game's own LAN and direct IP menus,", 'for a local network or a known address.')}


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
            if enabled:
                # 060q live: the light-blue hint stayed on the focused amber bar (design: navy). The DLL shows this navy
                # twin instead while its row has the focus (online_menus.cpp hub_focus_follow).
                text(key+'_hint_on',hint,181,142+39*i,113,15,'label',0)
                items[-1].update(align='right',hidden=True)
        # The help box follows the focused row (060q live: it always read HOST A GAME): one hidden set per focusable row,
        # the Host row's shown at the start (the Hub opens on it).
        panel('help_panel','',(43,334,266,74))
        for key,(head,line1,line2) in HUB_HELP.items():
            for part,value,y,h,style,color in (('_title',head,348,14,'label',5),('_1',line1,365,17,'body',4),('_2',line2,382,17,'body',4)):
                text('lc_help_'+key+part,value,59,y,240,h,style,color)
                if key!='host': items[-1]['hidden']=True
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
            button(key,label,(483,205+i*51,CODE_TOOL_WIDTH,46),intent, key!='done' or len(s.code)==8)
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
        for row in range(BROWSE_ROWS):
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


# Colours a focusable text item may rest in without an inline prefix (the style's color_nofocus; label's is 3, and RETRY / Copy
# code have always rested white on a label).
FOCUS_REST_COLORS = {'label': (3, 4)}


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
        # A focusable item's inline ~NN colour wins over the style's focus colour (060r live: Next page / Previous page were
        # pale blue on their own amber bar). The style's own resting colour needs no prefix: white for row / body, pale blue (3) for label.
        if value and (not e['intent'] or e['color'] not in FOCUS_REST_COLORS.get(e['style'],(4,))): value='~'+str(palette_ids[e['color']]).zfill(2)+value
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
            target,owner,rect,outline,_=focus_placement(screen,e)
            if root.find(f"item[@name='{target}']") is None:
                ET.SubElement(root,'item',name=target,type='MENU_ITEM_MODEL',model='ui/models/model_hide',neverfocus='true',animate='true')
            ET.SubElement(item,'onfocus',item=target,type='focus',model=focus_resource(rect,outline,focus_variant(screen,owner)),loop='1')
            if screen['name'] not in COMPACT_FOCUS_SCREENS:
                ET.SubElement(item,'onfocus',item=target,type='nofocus',model='ui/models/model_hide')
    return root


def tree_problems(root, screen, palette_ids=None):
    errors=layout_problems(screen); items={e.get('name'):e for e in root.findall('item')}
    if len(root.findall('.//onfocus'))>75: errors.append('retail onfocus record budget exceeded (75)')
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
    ET.SubElement(pkg,'xml',filename='ui/menus/'+(root.get('name') if root.get('type') in ('HOST_MENU','JOIN_MENU','GAME_OPTIONS_MENU') else root.get('igb')))
    # Model backdrops embed their pixels. A retired image= sprite must not
    # preload another 5 MiB copy of the page at every open.
    if root.get('image'):
        ET.SubElement(pkg,'texture',filename=root.get('image'))
    return pkg


def preview_text(value, device='pad'):
    """Synthetic device fixture, never a substitute for runtime token expansion.

    pad_prompts returns single coloured face-button letters, not round icons.
    Its Start and keyboard labels are bracketed names of the bound controls.
    """
    if device not in ('pad','keyboard'): raise ValueError('unknown preview device')
    labels={'$MENU_ACCEPT':'A','$MENU_BACK':'B','$MENU_OK':'[Start]',**PAD_TOKEN_BUTTONS} if device=='pad' else {
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
    # 060q live: a hit_rect used to become the item's layout box, and CText aligns the text in that box - so every button
    # with a hit_rect (lobby START GAME / KICK PLAYER / LEAVE, the Party rail, INVITE, Retry) drew its label at the bar's
    # left edge, START GAME's S under the bar's slanted end. The text box is the text's own rect now; the mouse uses the
    # drawn bars (Data/lc_online_hits.txt, fix E), which never depended on this box.
    for e in screen['items']:
        if e['intent'] and (e['enabled'] or screen.get('runtime')):
            target,owner=focus_target(screen,e)
            layouts[target]=(shared_focus(owner.get('plane',-150))[1],(0,-1,1,0)) if screen['name'] in SHARED_FOCUS_SCREENS else layouts[owner['name']]
    return layouts


def _anchor(item):
    x,y,w,_=item['rect']
    return ((x+(w/2 if item.get('align')=='center' else 0))*.8,item.get('plane',-150),(480-y)*.8)


def focus_placement(screen,item):
    """(target, owner, model rect, outline, owner-relative rect). On a SHARED_FOCUS_SCREENS screen the model rect is
    the owner-relative focus rect moved into its plane's shared origin frame (the same bar on screen)."""
    target,owner=focus_target(screen,item)
    rect,outline=focus_spec(screen,owner)
    if screen['name'] not in SHARED_FOCUS_SCREENS: return target,owner,rect,outline,rect
    (ax,ay,az),(sx,sy,sz)=_anchor(owner),shared_focus(owner.get('plane',-150))[1]
    assert ay==sy and target==shared_focus(ay)[0]
    l,b,r,t=rect;dx,dz=ax-sx,az-sz
    return target,owner,(round(l+dx,4),round(b+dz,4),round(r+dx,4),round(t+dz,4)),outline,rect


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
    dll=(ctx.out/'dinput.dll').read_bytes() if (ctx.out/'dinput.dll').is_file() else b''
    anchor_capacity=engine_scene_anchors(ANCHOR_CAPABILITY if preview else dll)
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
                resource=variant_resource(screen,e)
                if resource not in focus_models:
                    focus_models[resource]=focus_model(focus_source.read_bytes(),rect,True,variant_picture(e))
            if e['intent'] and (e['enabled'] or screen.get('runtime')):
                _,owner,rect,outline,relative=focus_placement(screen,e)
                resource=focus_resource(rect,outline,focus_variant(screen,owner))
                if resource not in focus_models:
                    picture=focus_picture(screen,owner,relative) if outline else None
                    focus_models[resource]=focus_model(focus_source.read_bytes(),rect,outline,picture,slant=hit_lean(screen,owner['name']))
        extra={e.get('name'):(((-1000,-150,-1000)),(0,-1,1,0)) for e in tree.findall('item')
               if e.get('name') not in layouts}
        if name in LOBBIES:
            data=author_scene(source,screen,native_lobby_layouts(tree,screen),anchor_capacity=anchor_capacity)
        else:data=author_scene(source,screen,anchor_capacity=anchor_capacity)
        problems+=scene_problems(screen,data,anchor_capacity=anchor_capacity)
        if problems: raise ValueError('; '.join(problems))
        focus_models.update(backdrop_models(focus_source.read_bytes(),screen))
        add_backdrop(tree,screen['name'])
        pending.append((name,tree,data,texture(atlas.read_bytes(),render(screen,text=False,focus=False),name)))
    # Optional native-class presentation. Publish it under a separate name so
    # Menus=0, missing resources, or an unsupported native tree retain retail.
    from . import online_options as GO
    options_detail={'enabled':False,'fallback':'game_options'}
    try:
        option,models=GO.prepare(ctx,source,atlas.read_bytes(),focus_source.read_bytes(),ids,metrics,anchor_capacity)
    except (ValueError,OSError,KeyError) as error:
        options_detail['reason']=str(error)
    else:
        pending.append(option);focus_models.update(models)
        options_detail.update(enabled=True,menu=GO.MENU)
    from . import online_native_skins as NS
    native_skins = {}
    for name in NS.MENUS:
        detail = {'enabled':False,'fallback':name}
        try:
            if not preview and NS.capability(name) not in dll:
                raise ValueError('companion DLL lacks this native skin adapter')
            skin,models=NS.prepare(ctx,name,source,atlas.read_bytes(),focus_source.read_bytes(),ids,metrics,anchor_capacity)
        except (ValueError,OSError,KeyError) as error:
            detail['reason']=str(error)
        else:
            pending.append(skin);focus_models.update(models)
            detail.update(enabled=True,menu=NS.MENUS[name])
        native_skins[name]=detail
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
    hits=hit_table(authored_layouts)
    built={name:(tree,data) for name,tree,data,_ in pending}
    problems=hit_scene_problems(hits,list(authored_layouts),lambda n:built[n][0],lambda igb:next((d for t,d in built.values() if t.get('igb')==igb),None),
                                lambda resource:focus_models.get(resource))
    if problems: raise ValueError('mouse hit table vs the built focus bars: '+'; '.join(problems))
    ctx.write_bytes(HITS_FILE,hits,source='frontend:mouse hit boxes = drawn focus bars')
    if not preview:ctx.write_bytes('Data/lc_online_menus.cap',CAPABILITY,source='frontend:verified DLL menu capability')
    ctx.write_bytes('Data/lc_online_options.cap',GO.CAPABILITY if options_detail['enabled'] else b'',
                    source='frontend:optional native Game Options presentation')
    for name,detail in native_skins.items():
        ctx.write_bytes(NS.marker(name),NS.capability(name) if detail['enabled'] else b'',
                        source='frontend:optional native online presentation')
    report={'menus':list(MENUS),'colors':len(colors),'styles':len(styles),'palette_ids':ids,'font_probe':probe,
            'fixture_only':True,'enabled':not preview,'production_entry':F.PLAY_ONLINE_CMD,'layouts':authored_layouts,
            'commands':{name:{e['name']:command(intent_number(e['intent'])) for e in runtime_layout(name)['items'] if e['intent']} for name in MENUS},
            'intents':command_manifest(),'game_options':options_detail,'native_skins':native_skins}
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


# Live 060p: the four lc_ menus have no `type`, so the engine builds the base CMenu (vtable 0x69e41c,
# init 0x5af7b0), which never reads the menu `image` (only the derived init 0x5bb990 sets the manager's
# background sprite): black screen, text only. The lobby skins (HOST_MENU / JOIN_MENU) did get the sprite,
# but pinned to the 512 x 384 rect (pillarbox at 16:9) and upside down (texture() keeps top-down rows).
# Every screen now draws its art as two scene models instead, the path the Host segment pictures already
# proved in game: a full-height field wide enough for 2.5:1 (the hor+ view is aspect*384 wide, centred on
# 512) behind the 4:3 composition, both behind every focus bar (depth 40) and scene (planes -150/-170).
BACKDROP_ITEMS = ('lc_o_field', 'lc_o_backdrop')
BACKDROP_ANCHOR = (0, -150, 384)
BACKDROP_RECT = (0, -384, 512, 0)
FIELD_RECT = (-448, -384, 960, 0)
BACKDROP_DEPTH, FIELD_DEPTH = 120, 140


def backdrop_resource(name):
    return 'ui/models/lc_o_backdrop_'+name


def field_picture():
    """The composition's own vertical gradient (render()), one column: the field matches its rows."""
    from PIL import Image
    top=bytes.fromhex(PALETTE[1]); bottom=bytes.fromhex(PALETTE[0])
    column=Image.new('RGBA',(4,256))
    for y in range(256):
        a=(1-y/256)*.75
        column.paste(tuple(round(a*t+(1-a)*b) for t,b in zip(top,bottom))+(255,),(0,y,4,y+1))
    return column


def backdrop_models(focus_source, screen):
    art=render(screen,size=(1024,1024),text=False,focus=False).convert('RGBA')
    return {backdrop_resource(screen['name']):focus_model(focus_source,BACKDROP_RECT,True,art,depth=BACKDROP_DEPTH,slant=0),
            'ui/models/lc_o_field':focus_model(focus_source,FIELD_RECT,True,field_picture(),depth=FIELD_DEPTH,slant=0)}


def add_backdrop(tree, name):
    """First items of the tree (drawn first, deepest); the menu sprite is emptied (image="")."""
    tree.set('image','')
    for index,(item,model) in enumerate((('lc_o_field','ui/models/lc_o_field'),('lc_o_backdrop',backdrop_resource(name)))):
        tree.insert(index,ET.Element('item',name=item,type='MENU_ITEM_MODEL',model=model,neverfocus='true'))
    return tree


def backdrop_layouts():
    return {name:(BACKDROP_ANCHOR,(0,-1,1,0)) for name in BACKDROP_ITEMS}


def author_scene(source,screen,extra=None,*,anchor_capacity=ENGINE_SCENE_ANCHORS):
    """Author description aliases without colliding with retired source objects."""
    from . import menu_scene as S, igb_file as G
    existing={o.get(2) for o in G.IgbFile(source).objects_of('igTransform')}
    layouts={**backdrop_layouts(),**(extra or {}),**scene_layout(screen)}
    retired={name:'lc_o_source_'+name for name in layouts if name in existing and name!='button1'}
    if retired: source,_=M.rename_aliases(source,retired)
    return S.author_anchors(source,'button1',layouts,anchor_capacity=anchor_capacity)


def focus_resource(rect, outline=False, variant=''):
    # A small finite family, determined solely by the authored hit rectangle.
    return 'ui/models/lc_o_focus_'+('outline_' if outline else '')+'_'.join(str(round(v*10)) for v in rect)+variant


def _focus_images(graph, blocks, picture, solid):
    """One shared image for the panel's texture attributes; retire duplicate pixels.

    The owned flat topology has two images. All layers receive the same original
    artwork, so keeping two full RGBA images doubles disk and upload cost for no
    visual benefit. Keep object references valid with a 1x1 retired image.
    """
    import struct
    images = graph.objects_of('igImage')
    if not images:
        raise ValueError('focus model has no image')
    for attr in graph.objects_of('igTextureAttr'):
        if 12 not in attr.fields or attr.get(12) not in {o.ref for o in images}:
            raise ValueError('unsupported focus texture image binding')
        struct.pack_into('<i', graph.buf, attr.fields[12].offset, images[0].ref)
    for index, image in enumerate(images):
        art = picture.convert('RGBA') if picture is not None and index == 0 else None
        blob = art.tobytes() if art is not None else solid
        width, height = art.size if art is not None else (1, 1)
        for slot, value in {2:width,3:height,6:100,7:8,8:8,9:8,10:8,11:7,12:len(blob),19:width*4,20:0}.items():
            if slot in image.fields:
                struct.pack_into('<i', graph.buf, image.fields[slot].offset, value)
        blocks[image.get(13)] = blob


def focus_model(source, rect, outline=False, picture=None, depth=40, slant=None):
    """Fit owned flat topology to an original solid amber slanted focus bar.

    Live 060p: the engine draws these unlit models from their texture and ignores the vertex colour
    stream, so a solid bar's colour must be its 1x1 texel (it rendered white with an amber vertex colour).
    """
    import struct
    from . import igb_file as G, menu_scene as S
    data,_=M.fit_flat_panel(source,rect,border=1,opaque=True)
    g=G.IgbFile(data); blocks={}
    keep=blended_layer(g)
    solid=bytes.fromhex(PALETTE[5])+b'\xff'
    _focus_images(g, blocks, picture, solid)
    for o in g.objects_of('igMaterialAttr'):
        for slot in (5,6,7):
            if slot in o.fields: g.set_floats(o,slot,(1,1,1,1))
    for o in g.objects_of('igVertexArray1_1'):
        refs=g.ref_list(o.get(2)); vertices=g.block_floats(refs[0]); l,b,r,t=rect
        lean=(0 if outline or r-l<50 else FOCUS_LEAN) if slant is None else slant
        if o.ref!=keep:
            # 060q live: dialog.igb draws three layers - a 144-vertex frame with NO blend state (opaque: the picture's
            # transparent texels came out black = the black boxes / outline bars / light outer frames) and a 12-vertex
            # inset with an ADDITIVE blend (the lighter inner rectangles and the dark-rectangle layering). Only the one
            # alpha-blended quad may draw; the others collapse to a zero-area point (topology and references kept).
            vertices[:]=[l,depth,b]*(len(vertices)//3)
            g.set_block_floats(refs[0],vertices)
            if len(refs)>11 and refs[11] in g.blocks: g.set_block_floats(refs[11],[0.0]*(2*(len(vertices)//3)))
            if len(refs)>2 and refs[2] in g.blocks: blocks[refs[2]]=b'\xff'*4*o.get(3)
            continue
        # The kept quad sits inset in the source panel (its corner band); it spans the whole target rectangle now.
        xs=vertices[0::3];zs=vertices[2::3];lo_x,hi_x,lo_z,hi_z=min(xs),max(xs),min(zs),max(zs)
        for i in range(0,len(vertices),3):
            vertices[i]=l if vertices[i]-lo_x<hi_x-vertices[i] else r
            vertices[i+2]=b if vertices[i+2]-lo_z<hi_z-vertices[i+2] else t
        for i in range(0,len(vertices),3):
            vertices[i]+=lean*(vertices[i+2]-b)/(t-b)
            vertices[i+1]=depth  # relative to the anchor; 40 = behind text, in front of the backdrop
        g.set_block_floats(refs[0],vertices)
        if picture is not None:
            if len(refs)<=11 or refs[11] not in g.blocks: raise G.IgbError('focus image needs UV stream')
            uv=[]
            for i in range(0,len(vertices),3): uv.extend(((vertices[i]-l)/(r-l),(t-vertices[i+2])/(t-b)))
            g.set_block_floats(refs[11],uv)
        if len(refs)>2 and refs[2] in g.blocks:
            # White vertices: the texel (solid amber or the picture) is the colour on screen.
            blocks[refs[2]]=b'\xff'*4*o.get(3)
    for o in g.objects_of('igAABox'):
        l,b,r,t=rect
        g.set_floats(o,2,(l,depth,b));g.set_floats(o,3,(r+4,depth,t))
    import hashlib
    image_name='lc_o_focus_'+hashlib.sha256(picture.tobytes()).hexdigest()[:12] if picture is not None else 'lc_o_focus_amber'
    return namespace_images(S.static_model(g.rebuilt(blocks)),image_name)



def _layer_walk(g):
    """(vertex array ref, blend enabled, (src, dst) blend function) of every drawn layer, from the scene root down the
    attribute sets, inheriting blend state / function as the renderer does."""
    found=[];seen=set()
    def items(ref):
        return (g.list_items(ref) or []) if isinstance(ref,int) and ref>=0 else []
    def walk(ref,state,func):
        if ref in seen: return
        seen.add(ref);o=g.obj(ref)
        if o is None: return
        if o.name in ('igAttrSet','igGeometry'):
            for a in items(o.get(8)):
                at=g.obj(a)
                if at is None: continue
                if at.name=='igBlendStateAttr': state=bool(at.get(4))
                elif at.name=='igBlendFunctionAttr': func=(at.get(4),at.get(5))
                elif at.name=='igGeometryAttr1_5': found.append((at.get(4),state,func))
            for c in items(o.get(7)): walk(c,state,func)
    for info in g.objects_of('igSceneInfo'): walk(info.get(5),False,None)
    return found


def blended_layer(g):
    """The one vertex array of the flat panel drawn with ordinary alpha blending (SRC_ALPHA, ONE_MINUS_SRC_ALPHA).
    Refuses a panel whose layers are not one 4-vertex alpha-blended quad among the others."""
    from . import igb_file as G
    found=_layer_walk(g)
    alpha=[va for va,state,func in found if state and func==(4,5)]
    if len(found)!=len(g.objects_of('igVertexArray1_1')) or len(alpha)!=1 or g.obj(alpha[0]).get(3)!=4:
        raise G.IgbError('flat focus panel needs exactly one alpha-blended quad layer')
    return alpha[0]


def panel_layers(data):
    """(vertex count, blend enabled, blend function, zero area, (l, b, r, t)) per layer of a built model (output checks)."""
    from . import igb_file as G
    g=G.IgbFile(data);out=[]
    for va,state,func in _layer_walk(g):
        o=g.obj(va);v=g.block_floats(g.ref_list(o.get(2))[0])
        box=(min(v[0::3]),min(v[2::3]),max(v[0::3]),max(v[2::3]))
        out.append((o.get(3),state,func,box[0]==box[2] and box[1]==box[3],box))
    return out


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
    if screen.get('native_options'):
        # Identical native text hit rectangle and focus fill, including the
        # value column. The native Game Options mouse handler owns the click.
        return (-w*.4,-h*.8,w*.4,0) if item.get('align')=='center' else (0,-h*.8,w*.8,0),False
    if item['name'] in FLAT_FOCUS:
        return (0,-h*.8,w*.8,0),False
    if screen.get('party') and item.get('hit_rect'):
        # Rail rows, action bars and kick buttons: the focus fill is exactly the drawn control.
        hx,hy,hw,hh=item['hit_rect']
        return ((hx-x)*.8,-(hy+hh-y)*.8,(hx+hw-x)*.8,(y-hy)*.8),False
    if item['name'] in ('retry','lc_hostleft_again','lc_hostleft_back') and item.get('hit_rect'):
        # Retry and modal actions fill their authored control rectangle, leaving adjacent copy clear.
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
    if y>=FOOTER_TOP:
        # Footer prompts sit 2-5 layout units apart: the ordinary row's 12-unit ends covered the neighbouring prompts
        # (060q live: Browse's Refresh bar over "[Enter] Join" and "[Esc] Back"). Each end reaches at most to just short of
        # the middle of the gap to the next prompt (view units), never more than the row's 12.
        others=[e['rect'] for e in screen['items'] if e is not item and e['intent'] and e['rect'][1]>=FOOTER_TOP]
        left_gap=min([x-(o[0]+o[2]) for o in others if o[0]+o[2]<=x]+[30])
        right_gap=min([o[0]-(x+w) for o in others if o[0]>=x+w]+[30])
        pad=lambda gap: max(0.0,min(12.0,round(gap*.8/2-FOOTER_CLEAR,2)))
        return (-pad(left_gap),-h*.8-2,w*.8+pad(right_gap),5),False
    return (-12,-h*.8-2,w*.8+12,5),False


FOOTER_TOP, FOOTER_CLEAR = 440, 0.2


def focus_target(screen, item):
    """(focus anchor item name, entry that sizes the focus model). The cells of one Browse row share one owner (cell 0)
    and, on a SHARED_FOCUS_SCREENS screen, every focusable item shares the one SHARED_FOCUS model item."""
    m=re.fullmatch(r'room_(\d)_(\d)',item['name']) if screen['name']=='lc_browse' else None
    owner=next((e for e in screen['items'] if e['name']=='room_'+m.group(1)+'_0'),item) if m else item
    if screen['name'] in SHARED_FOCUS_SCREENS: return shared_focus(owner.get('plane',-150))[0],owner  # one model item per plane (060q)
    if m: return 'room_'+m.group(1)+'_focus',owner
    return item['name']+'_focus',item


def anchor_count(data):
    """Anchors the engine's playfield build (0x5882e0 -> walk 0x587f90) collects from an authored menu scene.

    The walk starts at the scene root, recurses into every group's children and adds each igUserInfo node carrying
    an ItemName property; ENGINE_SCENE_ANCHORS is the engine's capacity for them."""
    from . import igb_file as G
    g=G.IgbFile(data)
    def children(o):
        r=o.get(7)
        if not isinstance(r,int) or r<0: return []
        n=g.obj(r)
        if n is None or n.name!='igNodeList': return []
        b=n.get(4)
        return [g.obj(x) for x in g.ref_list(b)] if isinstance(b,int) and b>=0 else []
    def named(o):
        seen=set();stack=[f.value for f in o.fields.values() if f.type in ('igObjectRefMetaField','igMemoryRefMetaField')]
        while stack:
            r=stack.pop()
            if not isinstance(r,int) or r<0 or r in seen: continue
            seen.add(r);x=g.obj(r)
            if x is None:
                if r in g.blocks: stack.extend(g.ref_list(r))
                continue
            if x.name=='igStringKey' and x.get(2)=='ItemName': return True
            if x.name in ('igPropertyList','igProperty','igNameValue'):
                stack.extend(f.value for f in x.fields.values() if f.type in ('igObjectRefMetaField','igMemoryRefMetaField'))
        return False
    count=0;stack=[(g.obj(g.objects_of('igSceneInfo')[0].get(5)),0)]
    while stack:
        o,depth=stack.pop()
        if o is None or depth>64: continue
        if o.name=='igHashedUserInfo' and named(o): count+=1
        stack.extend((c,depth+1) for c in children(o))
    return count


def fit_text(text, width, measure):
    """Ellipsize within one field using the chosen renderer's width measurement."""
    if width<=0: raise ValueError('text field must have positive width')
    if measure(text)<=width: return text
    if measure('...')>width: return ''
    end=len(text)
    while end and measure(text[:end].rstrip()+'...')>width: end-=1
    return text[:end].rstrip()+'...'


def scene_problems(screen,data,*,anchor_capacity=ENGINE_SCENE_ANCHORS):
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
    anchors=anchor_count(data)
    if anchors>anchor_capacity:
        errors.append(f"{screen['name']}: {anchors} scene anchors, the engine holds {anchor_capacity} (0x5882e0)")
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
    return '_row'+item['name'].split('_')[1] if screen['name']=='lc_browse' and item['name'].startswith('room_') else '_footer' if item['rect'][1]>=FOOTER_TOP else ''


def focus_picture(screen,item,rect):
    """Row geometry retains badges/bars/diamonds when its steel fill is selected."""
    l,b,r,t=rect;x,y,_,_=item['rect']
    left,top=x+l/.8,y-t/.8;width,height=(r-l)/.8,(t-b)/.8
    selected=copy.deepcopy(screen);selected['selection']=(left,top,width,height)
    background=render(selected,size=(1920,1080),text=False,focus=True)
    return background.crop((round(left*3),round(top*2.25),round((left+width)*3),round((top+height)*2.25)))


# These probes describe additive APIs, not release or gameplay identities. Each
# must be present in ONE supplied DLL; separate menu/font DLLs cannot be stacked.
DLL_PROBES = (b'lc-online-menus/1\n', b'lc-online-input/1', b'lc-online-lobby/1', b'lc-online-broker/2', b'lc-online-native/1', b'lc-online-party/1', b'lc-online-errors/1', b'lc-online-hits/2',
                b'lc_notice_started', b'lc-online-drop-in/1', b'lc-online-linked-rate/1',
              b'lcOnlineIntent\0', 'Online\0'.encode('utf-16le'),
              'Menus\0'.encode('utf-16le'), 'LegendsClassicFonts\0'.encode('utf-16le'),
              b'ui/fonts/lc_fonts_pc.xmlb\0', b'ui/fonts/lc_fonts_hd.xmlb\0',
              b'lc_title\0', b'lc_row\0', b'lc_body\0', b'lc_label\0',
              # Live 060p fixes: glyph scale per screen pixel (textscale is in 512 x 384 view units) and the
              # Menus=1 + LegendsClassicFonts=0 fallback to the native Play Online menus.
              b'lc-fonts-screen/1', b'LegendsClassicFonts is not active',
              # 0.6 preview fix E: the mouse hit boxes are the drawn focus bars (Data/lc_online_hits.txt, hit_table).
              b'lc-online-hits/1', ANCHOR_CAPABILITY)
CAPABILITY = b'lc-online-menus/1\n'
# Mouse hit boxes (xml2-fix online_menus_hits_rules.hpp). XMen2.exe hit-tests an item with the box its text is laid out in
# (0x5bc530 -> 0x5bc1b0); every focus bar here is larger than that box (an ordinary row: 12 units left and right, 5 above,
# 2 below), so the bar's top and both ends were dead (live 060p item 7). The builder lists each focusable item's drawn bar
# (absolute view units, x right, y up: left bottom right top) and the DLL hit-tests our screens against it.
HITS_CONTRACT = 'lc-online-hits/1'
HITS_SHAPE_CONTRACT = 'lc-online-hits/2'
HITS_FILE = 'Data/lc_online_hits.txt'
# The DLL parser's limits (online_menus_hits_rules.hpp parse / name_ok / number): ONE bad line makes it refuse the WHOLE table
# and the mouse hit boxes of every co-op screen go off. The builder holds itself to the same rules (hit_table_problems) and
# test_online_menus.py feeds its output through the DLL's own parser (xml2_online_hits_parse_test) and compares verdicts.
HITS_MAX_ENTRIES = 1024
HITS_MAX_LINE = 256
HITS_MAX_FILE = 256 * 1024
HITS_VIEW_LIMIT = 4096.0
HITS_NAME = re.compile(r'[A-Za-z0-9_]{1,63}')
HITS_NUMBER = re.compile(r'-?(?:[0-9]+\.?[0-9]*|\.[0-9]+)')
# focus_model: a wide solid bar leans right as it rises (the top edge is FOCUS_LEAN view units to the right of the bottom
# edge); table v2 also records this shear (v1 omitted the drawn right strip).
FOCUS_LEAN = 4


def hit_lean(screen, name):
    item=next((e for e in screen['items'] if e['name']==name),None)
    if item is None: return 0  # the table validator still diagnoses synthetic bad rows
    _,_,(l,b,r,t),outline,_=focus_placement(screen,item)
    return FOCUS_LEAN if not outline and (item['rect'][1]>=FOOTER_TOP or r-l>=50) else 0


def hit_rows(screen):
    """(item, left, bottom, right, top) for every item that draws a focus bar (menu_tree's condition), in item order:
    the bar each focus model draws (focus_placement's owner-relative rect at the owner's anchor). The cells of a Browse
    row share their row's bar, so the whole row is clickable; the first cell listed wins (they share the row's intent)."""
    rows=[]
    for e in screen['items']:
        if not (e['intent'] and (e['enabled'] or screen.get('runtime'))): continue
        # The native LISTBOX (Kick picker) hit-tests its own rows (0x5ba2b0); one bar for the whole list would pick row 1.
        if e['intent']=='native-picker': continue
        _,owner,_,_,(l,b,r,t)=focus_placement(screen,e)
        ax,_,az=_anchor(owner)
        rows.append((e['name'],round(ax+l,4),round(az+b,4),round(ax+r,4),round(az+t,4)))
    return rows


def hit_unlisted_boxes(screen):
    """(item, left, bottom, right, top) in view units of the focusable items the table does not list: the Kick picker
    LISTBOX (its rows answer through 0x5ba2b0 / 0x5c8da0)."""
    boxes=[]
    for e in screen['items']:
        if e['intent']!='native-picker': continue
        x,y,w,h=e['rect']
        boxes.append((e['name'],x*.8,(480-y-h)*.8,(x+w)*.8,(480-y)*.8))
    return boxes


def _hit_number(v):
    text=('%.4f' % v).rstrip('0').rstrip('.')
    return '0' if text in ('-0','') else text


def hit_table_problems(data):
    """Every reason the DLL's parser (online_menus_hits::parse) would refuse these bytes; [] when it accepts them. Same
    rules, written separately: LF only, no BOM, no blank line, single spaces, lines of at most HITS_MAX_LINE bytes, names
    [A-Za-z0-9_]{1,63}, plain decimals within +/-4096, left < right and bottom < top, every (menu, item) once, at most
    HITS_MAX_ENTRIES, a whole file of at most HITS_MAX_FILE bytes."""
    if len(data)>HITS_MAX_FILE: return ['table larger than %d bytes'%HITS_MAX_FILE]
    if data.startswith(b'\xef\xbb\xbf'): return ['byte order mark']
    if not data: return ['empty file']
    if not data.endswith(b'\n'): return ['last line not terminated']
    lines=data[:-1].split(b'\n')
    problems=[]
    shaped=lines[0]==HITS_SHAPE_CONTRACT.encode('ascii')
    if lines[0] not in (HITS_CONTRACT.encode('ascii'),HITS_SHAPE_CONTRACT.encode('ascii')): problems.append('line 1: bad header')
    seen=set()
    for number,raw in enumerate(lines[1:],2):
        if len(raw)>HITS_MAX_LINE: problems.append('line %d: line too long'%number); continue
        if b'\r' in raw: problems.append('line %d: carriage return'%number); continue
        try: line=raw.decode('ascii')
        except UnicodeDecodeError: problems.append('line %d: not ASCII'%number); continue
        fields=line.split(' ')
        if len(fields)!=(7 if shaped else 6) or '' in fields: problems.append('line %d: bad fields'%number); continue
        menu,item,*numbers=fields
        if not (HITS_NAME.fullmatch(menu) and HITS_NAME.fullmatch(item)): problems.append('line %d: bad name'%number); continue
        try:
            for token in numbers:
                if len(token)>24 or not HITS_NUMBER.fullmatch(token): raise ValueError(token)
            left,bottom,right,top=map(float,numbers[:4])
            lean=float(numbers[4]) if shaped else 0
        except ValueError: problems.append('line %d: bad number'%number); continue
        if any(abs(v)>HITS_VIEW_LIMIT for v in (left,bottom,right,top)): problems.append('line %d: number out of range'%number); continue
        if not (left<right and bottom<top): problems.append('line %d: empty or inverted rectangle'%number); continue
        if abs(lean)>64 or abs(left+lean)>HITS_VIEW_LIMIT or abs(right+lean)>HITS_VIEW_LIMIT:
            problems.append('line %d: bad lean'%number); continue
        if (menu,item) in seen: problems.append('line %d: duplicate entry'%number)
        seen.add((menu,item))
    if len(lines)-1>HITS_MAX_ENTRIES: problems.append('too many entries')
    if len(lines)<2: problems.append('no entries')
    return problems


def hit_table(screens):
    """The Data/lc_online_hits.txt bytes for {engine menu name: bound screen}. Raises ValueError for anything the DLL's
    parser would refuse (that would switch the mouse hit boxes of every co-op screen off), and for a bar that reaches an
    unlisted focusable item (the Kick picker): the engine could hand it the click."""
    lines=[HITS_SHAPE_CONTRACT]
    problems=[]
    for name,screen in screens.items():
        rows=hit_rows(screen)
        for item,*rect in rows:
            lines.append(' '.join([name,item,*map(_hit_number,rect),_hit_number(hit_lean(screen,item))]))
        for item,pl,pb,pr,pt in hit_unlisted_boxes(screen):
            for bar,l,b,r,t in rows:
                lean=hit_lean(screen,bar)
                if l+min(0,lean)<pr and pl<r+max(0,lean) and b<pt and pb<t:
                    problems.append('%s: bar %s [%g %g %g %g] reaches the unlisted focusable item %s [%g %g %g %g]'%(name,bar,l,b,r,t,item,pl,pb,pr,pt))
    data=('\n'.join(lines)+'\n').encode('ascii')
    problems+=hit_table_problems(data)
    if problems: raise ValueError('mouse hit table: '+'; '.join(problems))
    return data


def hit_table_rows(data):
    """{menu: {item: (left, bottom, right, top)}} of an accepted table."""
    problems=hit_table_problems(data)
    if problems: raise ValueError('mouse hit table: '+'; '.join(problems))
    rows={}
    for line in data.decode('ascii').split('\n')[1:-1]:
        menu,item,*numbers=line.split(' ')
        rows.setdefault(menu,{})[item]=tuple(map(float,numbers[:4]))
    return rows


def _model_bar(model):
    """(left, bottom, right, top) of a built focus model relative to its anchor: the bounds of its vertices."""
    from . import igb_file as G
    g=G.IgbFile(model); xs=[]; zs=[]
    for o in g.objects_of('igVertexArray1_1'):
        v=g.block_floats(g.ref_list(o.get(2))[0]); xs+=v[0::3]; zs+=v[2::3]
    if not xs: raise ValueError('focus model has no vertices')
    return min(xs),min(zs),max(xs),max(zs)


def _model_edges(model):
    """Bottom and top x endpoints of the one nondegenerate focus quad, read from actual model vertices."""
    from . import igb_file as G
    g=G.IgbFile(model)
    for o in g.objects_of('igVertexArray1_1'):
        v=g.block_floats(g.ref_list(o.get(2))[0]);points=list(zip(v[0::3],v[2::3]))
        bottom=min(z for x,z in points);top=max(z for x,z in points)
        if top-bottom<.01 or max(x for x,z in points)-min(x for x,z in points)<.01: continue
        low=[x for x,z in points if abs(z-bottom)<.001];high=[x for x,z in points if abs(z-top)<.001]
        if len(low)!=2 or len(high)!=2: raise ValueError('focus model is not a four-corner quad')
        return min(low),max(low),min(high),max(high)
    raise ValueError('focus model has no drawn quad')


def hit_scene_problems(data, names, read_tree, read_scene, read_model):
    """Compare the table with the focus bars as BUILT: for every item of each built menu tree that has a focus model
    (<onfocus type="focus" item=ANCHOR model=MODEL>), the bar is the model's own vertices placed at ANCHOR's transform in
    the built scene IGB - nothing from focus_placement. The table row must have the bar's left, bottom and top and a right
    edge and shear matching all four drawn corners, and the table must list
    exactly the items that have such a model (the Kick picker has none). Callables: read_tree(menu) -> XMLB root,
    read_scene(igb name) -> bytes, read_model(resource) -> bytes or None."""
    from . import igb_file as G
    rows=hit_table_rows(data)
    leans={(f[0],f[1]):float(f[6]) if len(f)==7 else 0 for f in (line.split() for line in data.decode('ascii').splitlines()[1:])}
    problems=[]
    tol=0.06
    for name in names:
        tree=read_tree(name)
        scene=read_scene(tree.get('igb'))
        if scene is None: problems.append(name+': built scene missing'); continue
        graph=G.IgbFile(scene)
        positions={o.get(2):o.get(8)[12:15] for o in graph.objects if o.name=='igTransform'}
        table=rows.get(name,{}); seen=set()
        for item in tree.findall('item'):
            for focus in item.findall('onfocus'):
                if focus.get('type')!='focus': continue
                key=item.get('name'); seen.add(key)
                anchor=positions.get(focus.get('item')); model=read_model(focus.get('model'))
                if anchor is None or model is None: problems.append('%s: %s: focus anchor or model missing in the built output'%(name,key)); continue
                x0,z0,x1,z1=_model_bar(model)
                bar=(anchor[0]+x0,anchor[2]+z0,anchor[0]+x1,anchor[2]+z1)
                row=table.get(key)
                if row is None: problems.append('%s: %s draws a focus bar but the table has no row'%(name,key)); continue
                l,b,r,t=row
                lean=leans[(name,key)]
                edges=tuple(anchor[0]+x for x in _model_edges(model))
                if abs(b-bar[1])>tol or abs(t-bar[3])>tol or any(abs(a-z)>tol for a,z in zip((l,r,l+lean,r+lean),edges)):
                    problems.append('%s: %s: table [%g %g %g %g] shear %g vs built bar [%g %g %g %g]'%(name,key,l,b,r,t,lean,*bar))
        for key in sorted(set(table)-seen): problems.append('%s: table row %s has no focus model in the built menu'%(name,key))
    for name in sorted(set(rows)-set(names)): problems.append('table lists an unknown menu: '+name)
    return problems


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
# Raised only on the Hub (name entry) or Join by code (paste / symbols / the offline fixture lookup); the DLL's
# show_notice falls back to lc_inline_error on a screen without the node, so Browse does not spend anchors on them.
BROWSE_UNREACHABLE_NOTICES = ('lc_notice_paste_invalid', 'lc_notice_code_invalid', 'lc_notice_name_invalid',
                              'lc_notice_profile_save', 'lc_notice_name_open', 'lc_notice_resolving', 'lc_notice_fixture',
                              # 060q: the clipboard is only read by Join by code's paste (code_input); unavailable comes
                              # from intent::unavailable (no Browse item carries it) or the Code screen's offline lookup.
                              # Every screen change clears the notice (tick_impl: destination -> error_visible=false).
                              'lc_notice_clipboard', 'lc_notice_unavailable',
                              # 0.6 preview fix E: shown only on the Hub, when the host's native Kick removed this guest.
                              'lc_notice_removed',
                              # 0.6 preview fix L: the Host screen's native setup found the service not answering (before any room existed).
                              'lc_notice_service_silent')
NOTICE_TEXT = {
    'lc_notice_started': 'This session has started; ask the host to return to the lobby',
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
    'lc_notice_relay': 'A TURN relay is required. No relay route is available.',
    'lc_notice_clipboard': 'Could not open the clipboard. Type the code instead.',
    # 0.6 preview fix E: a guest the host removed (its native Kick: removal notice 0x2b, reason 0x10ce, flag 1) sees this on the
    # Hub instead of the host-left panel (xml2-fix online_menus_rules kicked_by_host).
    'lc_notice_removed': 'The host removed you from the game.',
    # 0.6 preview fix L (060r live failure 5): Host > OPEN with the service down said the service was LOST during setup. Nothing was
    # lost - the service never answered before a room existed - so that case reads the same as the other no-answer messages.
    'lc_notice_service_silent': 'The online service did not answer. Try again.',
}
# 060r live (Join by code header): 'Room connected' did not fit the 67-unit badge field and was clipped to 'Room connecte'.
# The DLL binds this word while a room is committed (online_menus.cpp room_badge_text); the unit test measures it against the field.
ROOM_BADGE_TEXT = 'In a room'
DATA_NAMES = {'local_name', 'self_name', 'last_name', 'last_code', 'last_time',
              'code_value', 'code_remaining', *(f'cell{i}' for i in range(8)),
              # Round 5: every field the broker bridge binds is DATA (normal interned text, no gamevar owner).
              'service', 'self_state', 'browse_hint', 'browse_hint_on', 'room_name', 'preview_name', 'room_code', 'details_name',
              'details', 'broker_error', 'list_count', 'list_age', 'lc_host_max_players', 'lc_refusal_rules', 'lc_toast_name', *(f'room_{r}_{c}' for r in range(BROWSE_ROWS) for c in (*ROW_COLUMNS, 5))}
# Round 5b: the DLL selects ONE lc_broker_err_<cause> scene per failure (and hides Retry where retrying cannot help),
# one status / pip / build scene and a dim veil per Browse row, a count + age header and a connected-service scene.
# Round 15 completes the table (INGAME-DESIGN 3.3): the first eight keep their broker/2 meaning; the DLL's
# online_menus_rules::error_cause_key / cause_table are the other half of this contract (tests pin both).
ERROR_CAUSES = ('code_not_found', 'room_full', 'version_mismatch', 'rate_limited', 'timeout', 'offline', 'refused', 'generic',
                'pin_mismatch', 'code_expired', 'room_closed', 'test_mode', 'unsupported', 'busy', 'invalid_name', 'too_many_public_rooms', 'too_many_joins', 'session_started')
RETRYABLE_CAUSES = ('rate_limited', 'timeout', 'offline', 'generic', 'room_closed')
# What each cause tells the player to do next (the DLL's next_action; Retry is the only one that is a control).
NEXT_ACTION = {'code_not_found': 'edit_code', 'room_full': 'browse', 'version_mismatch': 'back', 'rate_limited': 'retry',
               'timeout': 'retry', 'offline': 'retry', 'refused': 'back', 'generic': 'retry', 'pin_mismatch': 'back',
               'code_expired': 'edit_code', 'room_closed': 'retry', 'test_mode': 'back', 'unsupported': 'other_ways',
               'busy': 'wait', 'invalid_name': 'back', 'too_many_public_rooms': 'close_room', 'too_many_joins': 'leave_game', 'session_started': 'lobby'}
# One word each action's copy must contain, so a cause can never name the wrong next step.
NEXT_WORD = {'retry': ('retry', 'try again'), 'edit_code': ('code',), 'browse': ('another game', 'browse'),
             'back': ('back', 'update', 'check', 'turn it off', 'turn off'), 'other_ways': ('other ways',), 'wait': ('wait',),
             'close_room': ('close one',), 'leave_game': ('leave another game',), 'lobby': ('lobby',)}
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
    'session_started': 'This session has started. Ask the host to return to the lobby.',
    'test_mode': 'TestMode is on, so online play is off. Turn it off.',
    'unsupported': 'Online needs a complete install. Use Other ways to play.',
    'busy': 'The network link is busy. Wait a moment, then repeat.',
    'invalid_name': 'Room name must be 1-32 plain characters. Go Back.',
    'too_many_public_rooms': 'You already host 2 public rooms from this network. Close one.',
    'too_many_joins': 'This network has no free player seats. Leave another game.',
}
# Failures that are transient limits or waits read amber; the rest are red (09-errors: Full is amber, the rest red).
AMBER_CAUSES = ('room_full', 'room_closed', 'rate_limited', 'busy', 'too_many_public_rooms', 'too_many_joins')
# Causes each screen's own operations can reach (Hub/Host never resolve a code or list rooms).
_HUB_CAUSES = ('rate_limited', 'timeout', 'offline', 'refused', 'generic', 'pin_mismatch', 'test_mode', 'unsupported', 'busy', 'too_many_public_rooms', 'too_many_joins')
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
           'refresh':18, 'open-room':19, 'retry':20, 'visibility':21, 'page:-1':22, 'page:1':23, 'join':31, 'drop-in':75}
BROKER_ROW_FIRST, BROKER_ROW_LAST = 24, 30
# Exact allowed screens of the round-5 intents (docs/online-menus.md table); anything else is a contract error.
BROKER_SCOPE = {75:('lc_host',), 18:('lc_browse',), 19:('lc_host',), 20:MENUS, 21:('lc_host',), 22:('lc_browse',), 23:('lc_browse',),
                **{n:('lc_browse',) for n in range(24,31)}, 31:('lc_browse',)}


def enabled(ctx):
    return hasattr(ctx,'opt') and ctx.opt('online_menus', 'off') == 'on'


def capability_problems(data):
    probes=DLL_PROBES if BROWSE_ROWS>5 else tuple(t for t in DLL_PROBES if t!=ANCHOR_CAPABILITY)
    return ['missing DLL probe: '+repr(token) for token in probes if token not in data]


# Round 8 (lc-online-party/1): the in-session Party screen. 68 and 70 are reserved; 63..74 exist on lc_party only.
PARTY_MENU = 'lc_party'
PARTY_INTENTS = {'party-resume':63,'party-invite':64,'party-propose':65,'party-leave':66,'party-leave-yes':67,'party-kick-yes':69,
                 **{f'party-kick:{n}':70+n for n in range(1,5)}}
PARTY_INTENT_NUMBERS = tuple(sorted(PARTY_INTENTS.values()))
PUBLIC_INTENTS = (*range(2,15),16,17,*range(18,32),*range(32,63),*PARTY_INTENT_NUMBERS,75)


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


# Where each screen's Retry control sits (the hit rectangle of the `retry` text item; it has no baked bar any more).
RETRY_RECT = {'lc_code': (489, 395, 62, 18), 'lc_browse': (43, 424, 56, 16)}
RETRY_DEFAULT = (527, 423, 62, 16)


def _error_node(name, cause):
    """lc_broker_err_<cause>: ONE plain hidden text item with the cause's one-line copy (warn colour).

    060q live: a hidden model scene (diamond + rule + panel + the copy as a baked texture part) never draws when the DLL
    un-hides it - the model keeps the invisible stand-in the engine's loader gave a start-hidden MENU_ITEM_MODEL - so the
    player saw only the diagnostic. Plain text items (the notices, the status lines) un-hide fine, so the copy is one."""
    warn = 5 if cause in AMBER_CAUSES else 7
    copy_ = ERROR_COPY[cause]
    retry_ok = cause in RETRYABLE_CAUSES
    if name == 'lc_code':
        rect = (111, 396, 268, 18)
        if cause in ('too_many_public_rooms', 'too_many_joins'):
            # Fit the cap copy while keeping the diagnostic's separate cell clear.
            rect = (111, 396, 280, 18)
    elif name == 'lc_browse':
        rect = (121, 425, 247, 15) if retry_ok else (59, 425, 309, 15)
    else:
        rect = (69, 424, 322, 16)
    return _entry('lc_broker_err_' + cause, copy_, rect, 'body', warn, hidden=True), RETRY_RECT.get(name, RETRY_DEFAULT)


def _row_scenes(items):
    """Per-row status diamond+word, player pips + neutral ping bars, build badge and the dim veil for unjoinable rows.

    Models are shared across the seven rows (identical relative art); each row only has its own anchor. They sit between
    the focus fill and the text (plane -170 -> depth -130); the veil sits in front of the text (-200 -> -160)."""
    for r in range(BROWSE_ROWS):
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
        # Inline description colors override focused styles. The DLL copies the
        # matching localized source into Select after native description refresh.
        for suffix,color in (('normal',4),('hover',0)):
            items.append(_entry('lc_hub_select_'+suffix,'$MENU_ACCEPT Select',(43,454,59,17),'body',color,hidden=True))
        items.append(_variant('lc_service_ok',(355,229,120,18),[dict(kind='diamond',rect=(0,3,7,6),color=6),
                              dict(text='Connected',rect=(12,0,100,18),style='row',color=6)],model_name='service_ok'))
    else:
        # The longest state the DLL binds is ROOM_BADGE_TEXT; the static diamond implied a connected service.
        by['self_state'].update(rect=(529,46,67,13))
        shapes[:]=[q for q in shapes if not(q['kind']=='diamond' and q['rect']==(529,49,7,6))]
        items.append(_variant('lc_service_ok',(529,46,67,13),[dict(kind='diamond',rect=(0,3,7,6),color=6),
                              dict(text='Connected',rect=(9,0,58,13),style='label',color=6)],model_name='service_ok'))
    status={'lc_online':(48,424,420,16),'lc_host':(48,424,420,16),'lc_code':(111,397,370,18),'lc_browse':(108,425,346,14)}[name]
    offline={'lc_online':(48,408,546,14),'lc_host':(48,408,546,14),'lc_code':(81,424,478,14),'lc_browse':(196,137,258,14)}[name]
    colors={'lc_broker_empty':3,'lc_broker_stale':5,'lc_broker_room':6,'lc_broker_offline_room':7}
    retry=RETRY_RECT.get(name,RETRY_DEFAULT)
    for key in BROKER_SCREENS[name]:
        if key.startswith('lc_broker_err_'):
            node,retry=_error_node(name,key[len('lc_broker_err_'):])
            items.append(node)
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
    # Default text colour: the item is drawn on the plain page (no baked bar behind it) and takes the native highlight on focus.
    e=_entry('retry','RETRY',(retry[0]+13,retry[1]+(retry[3]-12)/2,retry[2]-14,12),'label',4,intent='retry')
    e['enabled']=False;e['hidden']=True;e['hit_rect']=retry;items.append(e)
    diag={'lc_code':(382,399,104,14),'lc_browse':(370,425,227,14)}.get(name,(393,425,128,14))
    items.append(_entry('broker_error','',diag,'label',7,data=True,align='right'))
    if name=='lc_host':
        # Mutually exclusive localized visibility scenes: segment control + the preview badge. Private is the
        # DLL default (it also sets the pair itself when no service is live); the hit item below owns input (intent 21).
        for key in ('visibility','visibility_other','preview_visibility'):
            items.remove(by[key])
        shapes[:]=[q for q in shapes if q['rect'] not in ((148,167,65,23),(218,167,59,23),(533,168,46,14))
                   and not(q['kind']=='slash' and q['rect']==(31,248,4,45))]  # the CAMPAIGN-only marker: one scene per row now (_native_host_nodes)
        def scene(public):
            on,off=((70,0,59,23),(0,0,65,23)) if public else ((0,0,65,23),(70,0,59,23))
            labels=(('PUBLIC' if public else 'PRIVATE'),('PRIVATE' if public else 'PUBLIC'))
            # 060r live: the unselected chip's pale text sat directly on the amber VISIBILITY bar. It is a navy chip now (fill + the
            # same pale outline and text), so it reads on the amber bar and on the dark panel alike; the selected chip stays white / navy.
            return [dict(kind='rect',rect=on,color=4),dict(kind='rect',rect=off,color=0),dict(kind='outline',rect=off,color=3),
                    dict(text='PRIVATE',rect=(11,5,52,16),style='row',color=0 if not public else 3),
                    dict(text='PUBLIC',rect=(81,5,52,16),style='row',color=0 if public else 3),
                    dict(kind='outline',rect=(385,1,46,14),color=3),
                    dict(text='PUBLIC' if public else 'PRIVATE',rect=(391,3,50,14),style='label',color=3)]
        # 060q live: at the default plane the VISIBILITY focus bar (same plane, drawn later) covered both chips. The pair
        # sits in front of the focus fill and behind the text, as the Browse row scenes do.
        items.append(_variant('lc_host_private',(148,167,431,23),scene(False),plane=-170));items[-1]['hidden']=False
        items.append(_variant('lc_host_public',(148,167,431,23),scene(True),plane=-170))
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
        # List header: DATA fresh/stale count, DLL-ticked "Updated N s ago" at the right with the
        # five-segment refresh bar (the 10 s idle refresh interval); the track is static, the fills are scenes.
        items.remove(by['age'])
        by['list_header'].update(text='',rect=(59,137,132,13))
        items.append(_entry('list_count','',(59,137,132,14),'label',4,data=True))
        items.append(_entry('list_age','',(456,137,84,14),'label',3,data=True,align='right'))
        shapes[:]=[q for q in shapes if q['rect']!=(546,139,16,4)]
        for k in range(5):
            items.append(_variant(f'lc_age_fill{k+1}',(546+8*k,139,7,4),[dict(kind='rect',rect=(0,0,7,4),color=5)],model_name='age_fill'))
        _row_scenes(items)
        for row in range(BROWSE_ROWS):
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
           _bar((20,172,168,31),2),_bar((200,172,168,31),2)]
    items.append(_variant('lc_hub_host_left',(x,y,w,h),parts,model_name='host_left',plane=-280))
    for key,label,rect,intent,color in (('lc_hostleft_again',c['again'],(x+20,y+172,168,31),'open:lc_host',4),
                                         ('lc_hostleft_back',c['back'],(x+200,y+172,168,31),'dismiss',4)):
        e=_entry(key,label,(rect[0]+15,rect[1]+6,rect[2]-25,rect[3]-9),'row',color,intent=intent)
        e['enabled']=False;e['hidden']=True;e['hit_rect']=rect;e['plane']=-300;items.append(e)



# The focusable settings rows' side-marker positions (top y, layout units): visibility, room name, campaign (the fixture's baked slash).
# DROP-IN changes the current host admission policy before posting.
HOST_MARKER_ROWS = {'visibility': 155, 'room_name': 202, 'campaign': 248, 'drop':295}


def _native_host_nodes(screen,by):
    """Round 6 Host setup: settings are chosen in the native Game Options (intent 19 opens them), read back by the DLL and
    shown through hidden localized nodes at the approved anchors. The fixture prose the DLL clears is not authored."""
    items=screen['items']
    items[:]=[e for e in items if e['name'] not in HOST_FIXTURE_PROSE]
    # CAMPAIGN opens native options; DROP-IN is an editable host-only admission choice.
    by['campaign'].update(text='',intent='open-room')
    by['drop_in'].update(text='',intent='drop-in')
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
            [dict(text=word,rect=(0,0,198,18),style='row',color=3 if key.endswith('unknown') else 4),dict(text=why,rect=(0,19,210,15),style='body',color=3)],plane=-170))
    # 060r live (failure 7): the amber side marker was baked beside CAMPAIGN and stayed there while the focus bar sat on another row.
    # It is one hidden scene per settings row now (the same slash the fixture bakes: 4 wide, 45 tall, leaning right); the DLL shows the
    # focused row's (online_menus.cpp host_marker_follow) and none while focus is on the Open bar or a prompt.
    for key,y in HOST_MARKER_ROWS.items():
        items.append(_variant('lc_host_marker_'+key,(31,y,7,45),[_bar((0,0,6.5,45),5,2.5)]))
    # The player count: the DLL binds only the number (DATA); the label is static and sits at the old "Up to N players" line.
    items.append(_entry('lc_host_players_label','MAX PLAYERS',(415,194,92,14),'label',3))
    items.append(_entry('lc_host_max_players','',(512,191,60,18),'row',4,data=True))


def runtime_layout(name,state=None):
    """Production starts with no invented service, room, name or recent record."""
    screen=layout(name,state or Fixture(code='',rooms=[]))
    screen.update(runtime=True,fixture_only=False)
    # Short truthful fallbacks only: the DLL binds the live service/count/room values over these.
    replacements={'local_name':'Player','self_name':'Player','self_initial':'P',
        'self_state':'Connecting...','service':'Connecting...',
        'browse_hint':'Browse public games','browse_hint_on':'Browse public games','last_name':'','last_code':'',
        'identity':'Installed build: see launcher', 'code_state':'Not connected',
        'code_status':'Type or paste all eight symbols. The code is looked up automatically.',
        'preview_save':'Campaign selection pending',
        'preview_drop':'Friends join at the next area',
        'room_name':'Room name pending','preview_name':'Room pending',
        'save':'No campaign selected','campaign':'SELECT CAMPAIGN',
        'preview_visibility':'PENDING','open_hint':'Creates your room',
        'code_pending':'Share this code with friends','age':'',
        'list_header':'',
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
            # The prompts are the keyboard form; the DLL rebinds desctext3 / desctext4 to "Y Paste" / "X Clear" while a pad is shown.
            e['text']=('PASTE' if e['name']=='paste' else 'Ctrl+V Paste') if e['intent']=='paste' else (
                'CLEAR' if e['name']=='clear' else 'Shift+Del Clear')
    for shape in screen['shapes']:
        if shape['kind']=='diamond' and shape['color']==6:shape['color']=3
        if name=='lc_code' and shape['rect'][1]==130 and shape['rect'][3]==54:
            shape.update(kind='cell',outline=3)
        if name=='lc_code' and shape['rect']==(483,307,CODE_TOOL_WIDTH,46):shape['dim']=False
    if name in ('lc_code','lc_browse'):
        # Native descriptions expand MENU_BACK and add an explicit light
        # palette prefix. Keep localized sources for both visual states so
        # the DLL can restore navy on amber after description refresh.
        back=next(e for e in screen['items'] if e['name']==('desctext2' if name=='lc_code' else 'desctext3'))
        label=back['text']
        for suffix,color in (('normal',4),('hover',0)):
            screen['items'].append(_entry('lc_footer_back_'+suffix,label,back['rect'],back['style'],color,hidden=True))
    if name=='lc_code':
        # Only cell text/remaining count is published by input API /1. Neutral
        # cells avoid freezing the round-1 cursor at its initial edit position.
        screen['shapes']=[s for s in screen['shapes'] if not(s['color']==5 and
            s['rect'][1] in (130,172) and s['rect'][2]==45.5)]
    present={e['name'] for e in screen['items']}
    for key,value in NOTICE_TEXT.items():
        if name=='lc_browse' and key in BROWSE_UNREACHABLE_NOTICES: continue
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
    if name=='lc_online':
        for e in screen['items']:
            if e['name'] in ('lc_hostleft_again','lc_hostleft_back'):
                other='lc_hostleft_back' if e['name']=='lc_hostleft_again' else 'lc_hostleft_again'
                e.update(left=other,right=other,up=other,down=other)
    if name=='lc_browse':
        # The diagnostic owns the full right cell of the error row; paging has its
        # own footer cells instead of clipping the error against Previous page.
        for e in screen['items']:
            if e['name']=='scroll_up': e['rect']=(382,455,100,18)
            if e['name']=='scroll': e['rect']=(497,455,100,18)
            if e['name']=='breadcrumb': e['text']=''
        # Row cells keep the closed grid (left/right in a row, up/down in a column) while disabled or rebound.
        for e in screen['items']:
            m=re.fullmatch(r'room_([0-6])_([0-6])',e['name'])
            if not m or int(m.group(2)) not in ROW_COLUMNS: continue
            r,c=int(m.group(1)),int(m.group(2))
            i=ROW_COLUMNS.index(c)
            e.update(left=f'room_{r}_{ROW_COLUMNS[max(0,i-1)]}',right=f'room_{r}_{ROW_COLUMNS[min(len(ROW_COLUMNS)-1,i+1)]}',
                     up=f'room_{r-1}_{c}' if r else 'prompt_refresh',down=f'room_{r+1}_{c}' if r<BROWSE_ROWS-1 else 'scroll')
    if name=='lc_browse':
        next(e for e in screen['items'] if e['name']=='prompt_join')['down']='room_0_0'
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
            e=need(key,hide='true',type='MENU_ITEM_TEXT',neverfocus='true')
            if e is not None and _plain(e.get('text'))!=ERROR_COPY[key[len('lc_broker_err_'):]]: errors.append('error copy differs: '+key)
            continue
        e=need(key,hide='true',type='MENU_ITEM_TEXT',neverfocus='true')
        if e is not None and _plain(e.get('text'))!=broker_copy(name,key): errors.append('broker copy differs: '+key)
    for key in BROKER_VARIANTS:
        if key not in BROKER_SCREENS[name] and key in items: errors.append('unexpected broker node: '+key)
    for key,e in items.items():
        if 'fixture' in (e.get('text') or '').lower(): errors.append('fixture wording in production asset: '+key)
    if name=='lc_online':
        for key in ('service','browse_hint','browse_hint_on'): need(key,clamp='true')
        need('lc_hub_host_left',hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
        need('lc_hub_host_left_veil',hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
        need('lc_hostleft_again',usecmd=command(2),enabled='false',hide='true',type='MENU_ITEM_TEXT')
        need('lc_hostleft_back',usecmd=command(8),enabled='false',hide='true',type='MENU_ITEM_TEXT')
    elif 'lc_hub_host_left' in items: errors.append('the host-left panel belongs to the Hub')
    for key in NOTICE_TEXT:
        if name=='lc_browse' and key in BROWSE_UNREACHABLE_NOTICES:
            if key in items: errors.append('unreachable notice authored on Browse: '+key)
            continue
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
        e=need('drop_in',usecmd=command(75),type='MENU_ITEM_TEXT')
        if e is not None and e.get('text'): errors.append('drop-in prose comes from the policy scenes')
        for key in HOST_FIXTURE_PROSE:
            if key in items: errors.append('fixture prose left in the Host asset: '+key)
        for key in HOST_SETTING_COPY:
            e=need(key,hide='true',type='MENU_ITEM_TEXT',neverfocus='true')
            if e is not None and _plain(e.get('text'))!=HOST_SETTING_COPY[key]: errors.append('host setting copy differs: '+key)
        for key in ('lc_host_settings_unknown',*HOST_DROP_COPY,*('lc_host_marker_'+k for k in HOST_MARKER_ROWS)): need(key,hide='true',type='MENU_ITEM_MODEL',neverfocus='true')
        e=need('lc_host_max_players',clamp='true',type='MENU_ITEM_TEXT')
        if e is not None and any('gamevar' in k.lower() for k in e.attrib): errors.append('competing DATA owner: lc_host_max_players')
    if name=='lc_browse':
        for r in range(BROWSE_ROWS):
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
    text('lc_room_name','Online game',(61,127,245,22),'title')  # the DLL names the room (broker name, else the host's game) from the first tick
    shape('outline',(315,128,75,16),3)
    text('lc_room_visibility','PENDING',(320,130,65,14),'label',3)
    # 060r live: no "pending" copy for a guest or a LAN host - the campaign is the host's choice; the host's own DLL line names it.
    # p060fix/AE: the authored line claims no admission policy; the host's DLL line adds "Friends join at the next area" or
    # "No joining once the game starts" from the host's actual DROP-IN choice, and a guest never claims the remote policy.
    text('lc_campaign_summary','Campaign chosen in Game options.' if role=='host' else 'Campaign set by the host.',(61,153,375,18),color=3)
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
        text(prefix+'fps','',(x+10,y+57,112,12),'label',3,data=True,hidden=True)
        text(prefix+'fps_warning','',(x+10,y+71,112,12),'label',5,data=True,hidden=True)
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
    variant('lc_ready_all','All ready.',(125,365,420,17),'body',3,visible=fixture and not waiting and members>1)
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
    # 060q live: both were hidden model scenes (panel + baked copy) that never drew when un-hidden - the host saw only the
    # bare name over the ready line - so each is plain text now (the kind the engine un-hides correctly): the departed
    # guest's NAME (DLL data) with the copy on the line below it, and the service-lost line under the action bars. The DLL
    # hides the ready summary while a toast shows (they share the row).
    text('lc_lobby_guest_left',LOBBY_TOAST_COPY,(55,373,530,15),'body',3,hidden=True,plane=-300)
    text('lc_toast_name','',(55,357,530,15),'row',5,data=True,plane=-300)
    text('lc_lobby_service_lost',LOBBY_SERVICE_LOST_COPY,(69,431,520,15),'body',7,hidden=True,plane=-170)
    for key,label,rect,intent in (
        ('lc_leave_yes','Leave',(400,358,58,24),'leave-yes'),
        ('lc_leave_cancel','Cancel',(466,358,60,24),'dismiss'),
        ('lc_lobby_dismiss','Dismiss',(532,358,65,24),'dismiss')):
        e=text(key,label,rect,'body',intent=intent,hidden=True,plane=-300);e['enabled']=False
    text('desctext1','$MENU_BACK Leave' if role=='host' else '',(324,455,65,18))
    text('desctext2','$MENU_OTHER Kick player' if role=='host' else '$MENU_OTHER Ready / Unready',(106,455,110,18))
    text('desctext3','Ctrl+C Copy code',(221,455,98,18))  # the keyboard form; the DLL rebinds it to "Y Copy code" for a pad
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
    # 060s bound HOST/READY/SAME BUILD correctly, but their overlapping raster models shared the card's depth.
    # Native text supplies independent glyph draws in front of the card; the visible words do not depend on model ordering.
    card_labels={'host':'HOST','ready':'READY','not_ready':'NOT READY','you':'You','ms':'ms','measuring':'Measuring',
                 'same_build':'SAME BUILD','checking_build':'CHECKING BUILD...','other_build':'OTHER BUILD'}
    for e in items:
        match=re.fullmatch(r'lc_p([1-4])_(.+)',e['name'])
        if not match or match[2] not in card_labels: continue
        n=int(match[1]);suffix=match[2];x=43+(n-1)*141
        rects={'host':(x+90,195,33,14),'ready':(x+23,275,100,18),'not_ready':(x+23,275,100,18),
               'you':(x+26,293,96,16),'ms':(x+73,293,39,16),'measuring':(x+26,293,96,16)}
        e.update(text=card_labels[suffix],parts=[],plane=-190,rect=rects.get(suffix,e['rect']),enabled=False)
        # Never let a display label answer CMenu's mouse walk and raise Accept on the action focused elsewhere.
        # Inline palette prefixes retain the authored glyph colour even though this native item is disabled.
    _graph(screen)
    # Only offline previews reflect a gate. Authored Start must be available for
    # the native activator/tick to own enabling, and must keep its original flags.
    return screen


def variant_resource(screen,item):
    # Relative artwork is independent of its card/row anchor and screen. Share
    # identical pictures across all four Party cards and the native lobby skins.
    # Include every variant_picture input that can affect pixels or geometry.
    import hashlib, json
    visual = {key:item.get(key) for key in ('text','parts','picture_scale','dim','font_alias','align')}
    visual.update(size=item['rect'][2:], font=font_binding(item),
                  enabled=item.get('enabled',True), color=item['color'])
    digest=hashlib.sha256(json.dumps(visual,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
    return 'ui/models/lc_o_variant_'+digest


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
            # 060r live (failure 9): the native prompts (desctext1..5) kept animtext_scene="help", the native help bar's
            # fade-in, which this scene does not carry - not one lobby prompt (A Select / X Kick player / X Ready / Copy / B
            # Leave) was ever drawn. Every other reskin (codex, options, pause, the action buttons above) drops it too.
            item.attrib.pop('animtext_scene',None)
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
    dll=index.path('dinput.dll')
    anchor_capacity=engine_scene_anchors(dll.read_bytes() if dll else b'')
    marker=index.path('Data/lc_online_menus.cap')
    if marker is None or marker.read_bytes()!=CAPABILITY:errors.append('exact capability marker missing')
    from . import online_options as GO
    options=index.path('Data/lc_online_options.cap')
    optional=()
    if options is not None and options.read_bytes():
        if options.read_bytes()!=GO.CAPABILITY:errors.append('invalid Game Options capability marker')
        else:optional=(GO.MENU,)
    from . import online_native_skins as NS
    for name,variant in NS.MENUS.items():
        cap=index.path(NS.marker(name))
        if cap is not None and cap.read_bytes():
            if cap.read_bytes()!=NS.capability(name):errors.append('invalid native online skin marker: '+name)
            else:optional+= (variant,)
    for name in (*MENUS,*LOBBIES,PARTY_MENU,*optional):
        scene=name if name in (*MENUS,PARTY_MENU,GO.MENU,*NS.MENUS.values()) else 'lc_lobby_'+name
        for rel in [f'UI/menus/{name}.XMLB',f'UI/menus/{name}.engb',f'UI/menus/{scene}.IGB',
                    f'Textures/menus/{scene}.IGB',f'Packages/generated/maps/package/menus/{name}.PKGB']:
            if index.path(rel) is None:errors.append('missing '+rel)
        igb=index.path(f'UI/menus/{scene}.IGB')
        if igb is not None:
            # The engine's per-scene anchor capacity (0x5882e0): over it the playfield build corrupts memory (060p).
            try:
                anchors=anchor_count(igb.read_bytes())
                if anchors>anchor_capacity:errors.append(f'{scene}: {anchors} scene anchors, the engine holds {anchor_capacity}')
            except Exception as error:
                errors.append(scene+': unreadable scene ('+type(error).__name__+')')
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
    errors+=model_output_problems(out,index)
    return errors


def model_output_problems(out, index=None):
    """060q live (fix H): every LC model draws exactly one alpha-blended layer (dialog.igb's opaque frame and additive inset
    drew black boxes, outline bars and lighter inner rectangles)."""
    from pathlib import Path
    out=Path(out);errors=[]
    from . import menu_scene as S
    for path in sorted(p for p in (out/'UI'/'models').glob('*') if p.name.lower().startswith('lc_o_') and p.suffix.lower()=='.igb'):
        try:
            data=path.read_bytes()
            errors.extend(path.name+': '+problem for problem in S.static_model_problems(data))
            layers=panel_layers(data)
            drawn=[l for l in layers if not l[3]]
            if len(drawn)!=1 or not drawn[0][1] or drawn[0][2]!=(4,5):
                errors.append(path.name+': model must draw one alpha-blended layer, draws '+repr([(l[0],l[1],l[2]) for l in drawn]))
        except Exception as error:
            errors.append(path.name+': unreadable model ('+type(error).__name__+')')
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
