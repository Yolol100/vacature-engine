// Request only the register columns actually used for source gates and application dedupe.
// Rebuild the established row layout so the existing strict policy checks stay unchanged.
// All ranges start at row 1 with a nonempty header, preserving absolute row alignment.
export const REGISTER_COMPACT_RANGES=Object.freeze([
  "'Bronnen'!A1:A","'Bronnen'!M1:M",
  "'Vacatures'!A1:B","'Vacatures'!G1:H",
  "'Applications'!A1:A","'Applications'!C1:C","'Applications'!E1:E",
  "'ApplicationEvents'!A1:B","'ApplicationEvents'!D1:D","'ApplicationEvents'!F1:F"
]);

function projectRows(columns){
  const count=Math.max(0,...columns.map(([rows])=>rows.length));
  const out=new Array(count);
  for(let i=0;i<count;i++){
    const row=[];
    for(const [rows,offset,width] of columns){
      const cells=rows[i]||[];
      for(let j=0;j<width;j++)if(cells[j]!==undefined)row[offset+j]=cells[j];
    }
    out[i]=row;
  }
  return out;
}
export function expandRegisterRanges(chunks){
  if(!Array.isArray(chunks)||chunks.length!==REGISTER_COMPACT_RANGES.length)
    throw new Error('Spreadsheet header mismatch: stop before dedupe or writes');
  return [
    projectRows([[chunks[0],0,1],[chunks[1],12,1]]),
    projectRows([[chunks[2],0,2],[chunks[3],6,2]]),
    projectRows([[chunks[4],0,1],[chunks[5],2,1],[chunks[6],4,1]]),
    projectRows([[chunks[7],0,2],[chunks[8],3,1],[chunks[9],5,1]])
  ];
}
