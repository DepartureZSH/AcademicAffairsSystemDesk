// Reuse the existing web-derived picker verbatim; no second hand-written grid.
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const files=['scripts/course-editor-local-adapter.txt','apps/desktop/src/web-course-editor/useCourseEditor.ts'];
for(const file of files){
  const target=path.join(root,file);
  let text=fs.readFileSync(target,'utf8');
  const needle='subjectEditorOpen.value=true;await nextTick();';
  const replacement="if(props.context.pickerDraft){externalCoursePreferredDraft.value=props.context.pickerDraft;coursePreferredPickerTitle.value='专项期望时间设置';prepareCoursePreferredPicker();watch(showCoursePreferredPicker,open=>{if(!open)emit('close');});return;}subjectEditorOpen.value=true;await nextTick();";
  if(!text.includes('if(props.context.pickerDraft)')){
    if(!text.includes(needle))throw Error('Course editor lifecycle changed');
    text=text.replace(needle,replacement);
    fs.writeFileSync(target,text);
  }
}
const editor=fs.readFileSync(path.join(root,'apps/desktop/src/web-course-editor/CourseEditor.vue'),'utf8');
const start=editor.indexOf('<div v-if="showCoursePreferredPicker"');
if(start<0)throw Error('Picker boundary missing');
let depth=0,end=-1;
for(const match of editor.slice(start).matchAll(/<\/?div\b[^>]*>/g)){
  depth+=match[0].startsWith('</')?-1:1;
  if(depth===0){end=start+match.index+match[0].length;break;}
}
if(end<0)throw Error('Picker boundary invalid');
const script=editor.slice(0,editor.indexOf('</script>')+9).replace("from './useCourseEditor'","from '../web-course-editor/useCourseEditor'").replace("from './SearchableSelect.vue'","from '../web-course-editor/SearchableSelect.vue'");
fs.writeFileSync(path.join(root,'apps/desktop/src/components/AiExpectedTimePicker.vue'),script+'\n<template><Teleport to="body"><div class="web-course-editor">'+editor.slice(start,end)+'</div></Teleport></template>\n<style src="../web-course-editor/web-course-editor.css"></style>\n');
