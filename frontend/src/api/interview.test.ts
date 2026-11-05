import { describe, it, expect } from 'vitest'
import { readEvents, type StreamEvent } from './interview'

describe('POST SSE 读取', () => {
  it('保留跨分片的中文、事件边界与CRLF，忽略心跳', async () => {
    const source = new TextEncoder().encode(
      ': heartbeat\r\n\r\nevent: delta\r\ndata: {"text":"你好，罗盘🧭"}\r\n\r\nevent: done\ndata: {}\n\n',
    )
    const events: StreamEvent[] = []
    await readEvents(
      new ReadableStream({
        start(controller) {
          for (const byte of source) controller.enqueue(Uint8Array.of(byte))
          controller.close()
        },
      }),
      (event) => events.push(event),
    )
    expect(events).toEqual([
      { event: 'delta', data: { text: '你好，罗盘🧭' } },
      { event: 'done', data: {} },
    ])
  })
  it('拒绝不完整的最后事件，便于恢复持久化状态', async () => {
    await expect(
      readEvents(
        new ReadableStream({
          start(c) {
            c.enqueue(new TextEncoder().encode('event: delta\ndata: {"text":'))
            c.close()
          },
        }),
        () => {},
      ),
    ).rejects.toThrow('连接中断')
  })
})
