package com.example.sampleapp.service;

import com.example.sampleapp.dao.UserDao;
import com.example.sampleapp.model.User;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserServiceImpl implements UserService {

    @Autowired
    private UserDao userDao;

    @Override
    public User login(String username, String password) {
        User user = userDao.findByUsername(username);
        if (user == null) {
            return null;
        }
        return user;
    }

    @Override
    public User getUserById(Integer id) {
        return userDao.findById(id);
    }

    @Override
    @Transactional
    public void registerUser(User user) {
        userDao.insert(user);
    }

    @Override
    @Transactional
    public void updateUser(User user) {
        userDao.update(user);
    }
}
