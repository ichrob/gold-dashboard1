'use strict';

// A repeated synthetic manager heartbeat can rewrite the previous terminal
// status between the pre-click snapshot and the selected export. Only a
// terminal status following this export's own `reading` transition belongs to
// the action under test.
function terminalStatusAfter(events,afterWrite){
 const relevant=Array.isArray(events)?events.filter(event=>
  Number.isInteger(event?.write)&&event.write>afterWrite):[];
 const reading=relevant.findIndex(event=>event.state==='reading');
 if(reading<0)return null;
 const terminal=relevant.slice(reading+1).find(event=>
  event.state==='staged'||event.state==='error');
 return terminal?{write:terminal.write,state:terminal.state}:null;
}

module.exports={terminalStatusAfter};
