//! OpenAI-compatible SSE decoding. Only assistant text is emitted to the WebView.
use serde_json::{json, Value};
use std::collections::BTreeMap;

#[derive(Default)]
pub(crate) struct StreamMessage {
    content: String,
    calls: BTreeMap<u64, Value>,
    finished: bool,
}

impl StreamMessage {
    pub(crate) fn push(&mut self, data: &str) -> Result<Option<String>, String> {
        if data.trim() == "[DONE]" {
            self.finished = true;
            return Ok(None);
        }
        let chunk: Value = serde_json::from_str(data).map_err(|_| "AI 流式响应格式无效")?;
        if chunk.get("error").is_some() {
            return Err("AI 服务中断生成，请重试".into());
        }
        let Some(choice) = chunk.pointer("/choices/0") else {
            return Ok(None);
        };
        let delta = choice.get("delta").ok_or("AI 流式响应缺少内容")?;
        if let Some(role) = delta.get("role").and_then(Value::as_str) {
            if role != "assistant" {
                return Err("AI 响应角色无效".into());
            }
        }
        let text = delta.get("content").and_then(Value::as_str).unwrap_or("");
        self.content.push_str(text);
        if let Some(calls) = delta.get("tool_calls").and_then(Value::as_array) {
            for call in calls {
                let index = call
                    .get("index")
                    .and_then(Value::as_u64)
                    .ok_or("工具片段缺少序号")?;
                if index >= 24 {
                    return Err("本轮工具调用过多，请缩小范围".into());
                }
                let target = self.calls.entry(index).or_insert_with(
                    || json!({"id":"","type":"function","function":{"name":"","arguments":""}}),
                );
                for (pointer, fragment) in [
                    ("/id", call.get("id")),
                    ("/function/name", call.pointer("/function/name")),
                    ("/function/arguments", call.pointer("/function/arguments")),
                ] {
                    if let Some(fragment) = fragment.and_then(Value::as_str) {
                        let existing = target
                            .pointer(pointer)
                            .and_then(Value::as_str)
                            .unwrap_or("");
                        *target.pointer_mut(pointer).unwrap() =
                            json!(format!("{existing}{fragment}"));
                    }
                }
            }
        }
        if let Some(reason) = choice.get("finish_reason").and_then(Value::as_str) {
            if reason == "length" {
                return Err("回复达到模型输出上限，本轮未提交变更，请缩小范围".into());
            }
            if reason == "content_filter" {
                return Err("AI 服务未完成回复，本轮未提交变更".into());
            }
            self.finished = true;
        }
        Ok((!text.is_empty()).then(|| text.to_owned()))
    }

    pub(crate) fn finish(self) -> Result<Value, String> {
        if !self.finished {
            return Err("AI 流式连接提前结束，本轮未提交变更，请重试".into());
        }
        if self.content.is_empty() && self.calls.is_empty() {
            return Err("AI 没有返回内容，请重试".into());
        }
        if self.calls.values().any(|c| {
            c["id"].as_str().unwrap_or("").is_empty()
                || c["function"]["name"].as_str().unwrap_or("").is_empty()
        }) {
            return Err("AI 工具调用未完整返回，请重试".into());
        }
        Ok(
            json!({"role":"assistant","content":self.content,"tool_calls":self.calls.into_values().collect::<Vec<_>>()}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn joins_text_and_tool_fragments_without_executing() {
        let mut stream = StreamMessage::default();
        assert_eq!(
            stream
                .push(r#"{"choices":[{"delta":{"role":"assistant","content":"正在"}}]}"#)
                .unwrap(),
            Some("正在".into())
        );
        stream.push(r#"{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call1","function":{"name":"query_project_data","arguments":"{\"dataset\":"}}]}}]}"#).unwrap();
        stream.push(r#"{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\"school_data\"}"}}]},"finish_reason":"tool_calls"}]}"#).unwrap();
        let message = stream.finish().unwrap();
        assert_eq!(message["content"], "正在");
        assert_eq!(
            message["tool_calls"][0]["function"]["arguments"],
            "{\"dataset\":\"school_data\"}"
        );
    }
    #[test]
    fn truncated_stream_is_never_a_final_proposal() {
        let mut stream = StreamMessage::default();
        stream
            .push(r#"{"choices":[{"delta":{"content":"未完成"}}]}"#)
            .unwrap();
        assert!(stream.finish().is_err());
        assert!(StreamMessage::default()
            .push(r#"{"choices":[{"delta":{},"finish_reason":"length"}]}"#)
            .is_err());
        assert!(StreamMessage::default()
            .push(r#"{"choices":[{"delta":{"tool_calls":[{"index":999}]}}]}"#)
            .is_err());
    }
}
