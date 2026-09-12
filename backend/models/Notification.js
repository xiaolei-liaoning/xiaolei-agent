const mongoose = require('mongoose');

const notificationSchema = new mongoose.Schema({
  user: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  type: { type: String, enum: ['task-assigned', 'due-reminder', 'comment', 'status-change', 'mention'], required: true },
  title: { type: String, required: true },
  message: { type: String },
  task: { type: mongoose.Schema.Types.ObjectId, ref: 'Task' },
  read: { type: Boolean, default: false },
  createdAt: { type: Date, default: Date.now }
}, { timestamps: true });

notificationSchema.index({ user: 1, read: 1 });
notificationSchema.index({ user: 1, createdAt: -1 });

module.exports = mongoose.model('Notification', notificationSchema);
