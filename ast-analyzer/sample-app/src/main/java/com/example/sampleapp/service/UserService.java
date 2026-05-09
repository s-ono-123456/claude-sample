package com.example.sampleapp.service;

import com.example.sampleapp.model.User;

public interface UserService {
    User login(String username, String password);
    User getUserById(Integer id);
    void registerUser(User user);
    void updateUser(User user);
}
