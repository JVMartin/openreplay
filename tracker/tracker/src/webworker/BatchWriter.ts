import type Message from '../common/messages.gen.js'
import * as Messages from '../common/messages.gen.js'
import MessageEncoder from './MessageEncoder.gen.js'
import StringDictionary from './StringDictionary.js'

const SIZE_BYTES = 3
const MAX_M_SIZE = (1 << (SIZE_BYTES * 8)) - 1

export default class BatchWriter {
  private nextIndex = 0
  private beaconSize = 2 * 1e5 // Default 200kB
  private encoder = new MessageEncoder(this.beaconSize)
  private strDict = new StringDictionary()
  private readonly sizeBuffer = new Uint8Array(SIZE_BYTES)
  private isEmpty = true

  constructor(
    private readonly pageNo: number,
    private timestamp: number,
    private url: string,
    private readonly onBatch: (batch: Uint8Array) => void,
  ) {
    this.prepare()
  }

  private writeType(m: Message): boolean {
    return this.encoder.uint(m[0])
  }
  private writeFields(m: Message): boolean {
    return this.encoder.encode(m)
  }
  private writeSizeAt(size: number, offset: number): void {
    //boolean?
    for (let i = 0; i < SIZE_BYTES; i++) {
      this.sizeBuffer[i] = size >> (i * 8) // BigEndian
    }
    this.encoder.set(this.sizeBuffer, offset)
  }

  private prepare(): void {
    if (!this.encoder.isEmpty) {
      return
    }

    // MBTODO: move service-messages creation methods to webworker
    const batchMetadata: Messages.BatchMetadata = [
      Messages.Type.BatchMetadata,
      1,
      this.pageNo,
      this.nextIndex,
      this.timestamp,
      this.url,
    ]
    this.writeType(batchMetadata)
    this.writeFields(batchMetadata)
    this.isEmpty = true
  }

  private writeWithSize(message: Message): boolean {
    const e = this.encoder
    if (!this.writeType(message) || !e.skip(SIZE_BYTES)) {
      // app.debug.log
      return false
    }
    const startOffset = e.getCurrentOffset()
    const wasWritten = this.writeFields(message)
    if (wasWritten) {
      const endOffset = e.getCurrentOffset()
      const size = endOffset - startOffset
      if (size > MAX_M_SIZE) {
        console.warn('OpenReplay: max message size overflow.')
        return false
      }
      this.writeSizeAt(size, startOffset - SIZE_BYTES)

      e.checkpoint()
      this.isEmpty = this.isEmpty && message[0] === Messages.Type.Timestamp
      this.nextIndex++
    }
    // app.debug.log
    return wasWritten
  }

  private beaconSizeLimit = 1e6
  setBeaconSizeLimit(limit: number) {
    this.beaconSizeLimit = limit
  }

  private applyDict(str: string): number {
    const [key, isNew] = this.strDict.getKey(str)
    if (isNew) {
      this.writeMessage([Messages.Type.StringDict, key, str])
    }
    return key
  }

  writeMessage(message: Message) {
    if (message[0] === Messages.Type.Timestamp) {
      this.timestamp = message[1] // .timestamp
    }
    if (message[0] === Messages.Type.SetPageLocation) {
      this.url = message[1] // .url
    }
    if (message[0] === Messages.Type.SetNodeAttribute) {
      message = [
        Messages.Type.SetNodeAttributeDict,
        message[1],
        this.applyDict(message[2]),
        this.applyDict(message[3]),
      ] as Messages.SetNodeAttributeDict
    }
    if (this.writeWithSize(message)) {
      return
    }
    // buffer overflow, send already written data first then try again
    this.finaliseBatch()
    if (this.writeWithSize(message)) {
      return
    }
    // buffer is too small. Create one with maximal capacity
    this.encoder = new MessageEncoder(this.beaconSizeLimit)
    this.prepare()
    if (!this.writeWithSize(message)) {
      console.warn('OpenReplay: beacon size overflow. Skipping large message.', message, this)
    }
    // reset encoder to normal size
    this.encoder = new MessageEncoder(this.beaconSize)
    this.prepare()
  }

  finaliseBatch() {
    if (this.isEmpty) {
      return
    }
    this.onBatch(this.encoder.flush())
    this.prepare()
  }

  clean() {
    this.encoder.reset()
  }
}
