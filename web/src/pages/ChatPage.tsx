import { useEffect, useMemo, useState } from "react";
import { App, Button, Card, Image, Input, Select, Segmented, Space, Switch, Tag, Upload } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { ImagePlus, Play, Trash2 } from "lucide-react";
import { api } from "../api";

type Mode = "chat" | "img";

type UploadedImage = {
  uid: string;
  name: string;
  mime: string;
  dataUrl: string;
};

type OutputImage = {
  url: string;
  b64_json?: string;
};

function readAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

function textFromChatPayload(payload: unknown) {
  const item = payload as { choices?: Array<{ message?: { content?: string }; delta?: { content?: string } }> };
  const choice = item.choices?.[0];
  return choice?.message?.content || choice?.delta?.content || "";
}

function imagesFromPayload(payload: unknown): OutputImage[] {
  const data = (payload as { data?: Array<{ url?: string; b64_json?: string }> }).data;
  if (!Array.isArray(data)) return [];
  return data
    .map((item) => ({
      url: item.url || (item.b64_json ? `data:image/png;base64,${item.b64_json}` : ""),
      b64_json: item.b64_json,
    }))
    .filter((item) => item.url);
}

function chunkText(payload: unknown, mode: Mode) {
  if (mode === "chat") return textFromChatPayload(payload);
  return String((payload as { progress_text?: string; message?: string }).progress_text || (payload as { message?: string }).message || "");
}

function chunkImages(payload: unknown) {
  const direct = imagesFromPayload(payload);
  if (direct.length) return direct;
  const data = (payload as { data?: Array<{ b64_json?: string; url?: string }> }).data;
  if (!Array.isArray(data)) return [];
  return imagesFromPayload({ data });
}

function buildChatBody(model: string, prompt: string, stream: boolean, images: UploadedImage[]) {
  const content: Array<Record<string, unknown>> = [{ type: "text", text: prompt }];
  images.forEach((image) => {
    content.push({ type: "image_url", image_url: { url: image.dataUrl } });
  });
  return {
    model,
    stream,
    messages: [{ role: "user", content }],
  };
}

function buildImageBody(model: string, prompt: string, stream: boolean, images: UploadedImage[]) {
  return {
    model: model || "gpt-image-2",
    prompt,
    stream,
    response_format: "b64_json",
    images: images.map((image) => ({ image_url: image.dataUrl, mime_type: image.mime, filename: image.name })),
  };
}

export default function ChatPage() {
  const { message } = App.useApp();
  const [mode, setMode] = useState<Mode>("chat");
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("proxy-debug-key") || "");
  const [models, setModels] = useState<string[]>(["auto", "gpt-image-2"]);
  const [model, setModel] = useState("auto");
  const [prompt, setPrompt] = useState("");
  const [stream, setStream] = useState(true);
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState("");
  const [rawLog, setRawLog] = useState("");
  const [outputImages, setOutputImages] = useState<OutputImage[]>([]);

  useEffect(() => {
    api.getSettings()
      .then((config) => {
        const configured = config.reverse_proxy?.models || [];
        const next = Array.from(new Set(["auto", ...configured, "gpt-image-2"])).filter(Boolean);
        setModels(next);
        setModel((current) => next.includes(current) ? current : next[0] || "auto");
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    localStorage.setItem("proxy-debug-key", apiKey);
  }, [apiKey]);

  useEffect(() => {
    if (mode === "img" && model === "auto") setModel(models.includes("gpt-image-2") ? "gpt-image-2" : models[0] || "gpt-image-2");
  }, [mode, model, models]);

  const endpoint = useMemo(() => {
    if (mode === "chat") return "/v1/chat/completions";
    return images.length ? "/v1/images/edits" : "/v1/images/generations";
  }, [mode, images.length]);

  const uploadImage = async (file: File) => {
    if (!file.type.startsWith("image/")) {
      message.error("只能上传图片");
      return Upload.LIST_IGNORE;
    }
    const dataUrl = await readAsDataUrl(file);
    const uid = `${file.name}-${file.lastModified}`;
    const uploadItem: UploadFile = { uid, name: file.name, status: "done", url: dataUrl };
    setImages((current) => [...current, { uid, name: file.name, mime: file.type, dataUrl }].slice(0, 4));
    setFileList((current) => [...current, uploadItem].slice(0, 4));
    return false;
  };

  const clearResult = () => {
    setAnswer("");
    setRawLog("");
    setOutputImages([]);
  };

  const send = async () => {
    if (!apiKey.trim()) {
      message.error("先填写代理 API Key");
      return;
    }
    if (!prompt.trim()) {
      message.error("请输入 Prompt");
      return;
    }
    clearResult();
    setLoading(true);
    try {
      const body = mode === "chat" ? buildChatBody(model, prompt, stream, images) : buildImageBody(model, prompt, stream, images);
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${apiKey.trim()}`,
        },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);

      if (!stream) {
        const payload = await resp.json();
        setRawLog(JSON.stringify(payload, null, 2));
        setAnswer(mode === "chat" ? textFromChatPayload(payload) : String(payload.message || ""));
        setOutputImages(imagesFromPayload(payload));
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("浏览器不支持读取流式响应");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || "";
        for (const frame of frames) {
          const lines = frame.split("\n").map((line) => line.trim()).filter(Boolean);
          const dataLine = lines.find((line) => line.startsWith("data:"));
          if (!dataLine) continue;
          const data = dataLine.slice(5).trim();
          setRawLog((current) => `${current}${frame}\n\n`);
          if (!data || data === "[DONE]") continue;
          try {
            const payload = JSON.parse(data);
            const text = chunkText(payload, mode);
            if (text) setAnswer((current) => current + text);
            const nextImages = chunkImages(payload);
            if (nextImages.length) setOutputImages((current) => [...current, ...nextImages]);
          } catch {
            setAnswer((current) => current + data);
          }
        }
      }
    } catch (e) {
      message.error((e as Error).message);
      setRawLog((current) => `${current}\nERROR: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-stack">
      <div className="section-head">
        <div>
          <h2 className="section-title">对话调试</h2>
          <p className="section-desc">单轮调试 OpenAI 兼容 Chat 和图片接口，支持流式与非流式响应。</p>
        </div>
        <Space>
          <Tag>{endpoint}</Tag>
          <Switch checked={stream} onChange={setStream} checkedChildren="流式" unCheckedChildren="非流式" />
        </Space>
      </div>

      <div className="chat-debug-layout">
        <Card className="surface" title="请求">
          <div className="form-grid two">
            <div className="field">
              <label>接口模式</label>
              <Segmented
                block
                value={mode}
                onChange={(value) => setMode(value as Mode)}
                options={[
                  { value: "chat", label: "Chat" },
                  { value: "img", label: "Img" },
                ]}
              />
            </div>
            <div className="field">
              <label>模型</label>
              <Select
                showSearch
                value={model}
                onChange={setModel}
                options={models.map((item) => ({ value: item, label: item }))}
              />
            </div>
          </div>

          <div className="field mt-3">
            <label>代理 API Key</label>
            <Input.Password value={apiKey} placeholder="sk-..." onChange={(event) => setApiKey(event.target.value)} />
          </div>

          <div className="field mt-3">
            <label>Prompt</label>
            <Input.TextArea
              value={prompt}
              rows={7}
              placeholder={mode === "chat" ? "输入单轮对话内容" : "输入图片生成或编辑提示词"}
              onChange={(event) => setPrompt(event.target.value)}
            />
          </div>

          <div className="field mt-3">
            <label>上传图片</label>
            <Upload
              listType="picture-card"
              multiple
              maxCount={4}
              fileList={fileList}
              beforeUpload={uploadImage}
              onRemove={(file) => {
                setImages((current) => current.filter((item) => item.uid !== file.uid));
                setFileList((current) => current.filter((item) => item.uid !== file.uid));
              }}
            >
              {fileList.length >= 4 ? null : <div className="upload-trigger"><ImagePlus className="size-5" /><span>图片</span></div>}
            </Upload>
            <p>{mode === "chat" ? "Chat 模式会把图片放进 user message content。" : "Img 模式有图片时调用 edits，无图片时调用 generations。"}</p>
          </div>

          <Space className="mt-4">
            <Button type="primary" icon={<Play className="size-4" />} loading={loading} onClick={send}>发送</Button>
            <Button icon={<Trash2 className="size-4" />} onClick={clearResult}>清空结果</Button>
          </Space>
        </Card>

        <Card className="surface" title="响应">
          <div className="chat-debug-output">
            <strong>Assistant</strong>
            <pre>{answer || "等待响应"}</pre>
          </div>

          {outputImages.length > 0 && (
            <div className="chat-debug-images">
              {outputImages.map((item, index) => (
                <Image key={`${index}-${item.url.slice(0, 48)}`} src={item.url} />
              ))}
            </div>
          )}

          <div className="chat-debug-output mt-3">
            <strong>Raw</strong>
            <pre>{rawLog || "等待原始响应"}</pre>
          </div>
        </Card>
      </div>
    </div>
  );
}
